"""Graph router — article reference graph API + viewer."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.services.graph_builder import GraphBuilder

router = APIRouter(prefix="/graph", tags=["Graph"])

_builder = GraphBuilder()


@router.get("", response_class=HTMLResponse)
async def graph_viewer(
    corpus_id: str = Query("", description="Collection to display"),
    query: str = Query("", description="Focus query"),
):
    """Serve the Cytoscape.js graph viewer."""
    import os
    viewer_path = os.path.join(os.path.dirname(__file__), "..", "static", "graph_view.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="Graph viewer not found")
    with open(viewer_path) as f:
        return HTMLResponse(content=f.read())


@router.get("/data")
async def graph_data(
    corpus_id: str = Query("", description="Collection name"),
    query: str = Query("", description="Search text to filter nodes"),
    max_nodes: int = Query(80, ge=5, le=500),
    min_weight: float = Query(0.0, ge=0.0),
):
    """Graph data in GraphDataResponse format (compatible with grafragexp Cytoscape.js viewer)."""
    if not corpus_id:
        raise HTTPException(status_code=400, detail="corpus_id is required")

    return _builder.to_graph_data_response(
        collection=corpus_id,
        query=query,
        max_nodes=max_nodes,
        min_weight=min_weight,
    )


@router.get("/{collection}/related")
async def related_articles(
    collection: str,
    article: str = Query(..., description="Article ID (e.g., L421-1)"),
    depth: int = Query(1, ge=0, le=5, description="Number of hops"),
):
    """Get a subgraph around a specific article."""
    subgraph = _builder.get_subgraph(collection, [article], depth=depth)
    if not subgraph:
        raise HTTPException(status_code=404, detail=f"No graph for collection '{collection}'")

    nodes = []
    for node_id, attrs in subgraph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "label": attrs.get("label", node_id),
            "livre": attrs.get("livre", ""),
            "titre": attrs.get("titre", ""),
            "chapitre": attrs.get("chapitre", ""),
            "referenced_by": attrs.get("referenced_by", []),
            "is_focus": node_id == article,
        })

    edges = []
    for source, target, attrs in subgraph.edges(data=True):
        edges.append({
            "source": source,
            "target": target,
            "description": attrs.get("description", "cite"),
        })

    return {
        "focus": article,
        "depth": depth,
        "collection": collection,
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/config")
async def graph_config():
    """Config for the graph viewer."""
    from app.config import settings
    return {
        "api_base_url": settings.myrag_public_url,
        "graphrag_viewer_url": settings.graphrag_viewer_url,
    }


@router.post("/{collection}/build")
async def build_graph(collection: str):
    """Build or rebuild the graph for a collection from its indexed chunks."""
    from app.services.openrag_client import OpenRAGClient

    client = OpenRAGClient()

    # Search all documents in the collection
    try:
        results = await client.search(collection, query="*", top_k=5000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search OpenRAG: {e}")

    documents = results.get("documents", [])
    if not documents:
        raise HTTPException(status_code=404, detail=f"No documents in collection '{collection}'")

    # Convert OpenRAG documents to chunk format
    chunks = []
    for doc in documents:
        meta = doc.get("metadata", {})
        filename = meta.get("filename", "")
        # Extract article ID from filename (Article-L421-1.md → L421-1)
        article = ""
        if filename.startswith("Article-") or filename.startswith("Article_"):
            article = filename.replace("Article-", "").replace("Article_", "").replace(".md", "")

        if article:
            # Re-extract references from content
            from app.services.graph_builder import extract_references
            references = extract_references(doc.get("content", ""))
            references = [r for r in references if r != article]

            chunks.append({
                "content": doc.get("content", ""),
                "filename": filename,
                "metadata": {
                    "article": article,
                    "livre": meta.get("livre", ""),
                    "titre": meta.get("titre", ""),
                    "chapitre": meta.get("chapitre", ""),
                    "references": references,
                    "parent_path": meta.get("parent_path", ""),
                },
            })

    # Build and save graph
    graph = _builder.build(collection, chunks)
    _builder.save(collection)

    return {
        "status": "built",
        "collection": collection,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
    }


@router.post("/{collection}/summarize")
async def summarize_articles(
    collection: str,
    threshold: int | None = Query(None, description="Override threshold (default: from collection config)"),
    llm_url: str = Query("", description="LLM API URL (default: Scaleway)"),
    llm_api_key: str = Query("", description="LLM API key"),
    llm_model: str = Query("", description="LLM model name"),
):
    """Generate AI summaries for long articles in the graph.

    Uses the collection's ai_summary_enabled and ai_summary_threshold settings.
    Override threshold via query param.
    Articles shorter than the threshold keep their raw 500-char preview.
    Articles longer get a 3-5 sentence AI summary with a 'Resume par l'IA' badge.
    Requires LLM access (Scaleway or OpenAI-compatible endpoint).
    """
    from app.models.collection import CollectionConfig

    config = CollectionConfig.load(collection)
    if config and not config.ai_summary_enabled and threshold is None:
        return {
            "status": "disabled",
            "detail": f"AI summaries are disabled for '{collection}'. Enable in collection config.",
        }

    effective_threshold = threshold or (config.ai_summary_threshold if config else 1000)
    from app.services.chunker import chunk_by_article

    graph = _builder.get(collection)
    if not graph:
        raise HTTPException(status_code=404, detail=f"No graph for '{collection}'. Build it first.")

    # Count articles that need summarizing
    long_articles = [n for n, d in graph.nodes(data=True)
                     if d.get("content_full_length", 0) > effective_threshold]

    if not long_articles:
        return {"status": "nothing_to_summarize", "threshold": effective_threshold}

    # We need the full chunks to summarize — re-read from source if available
    from pathlib import Path
    source_files = list(Path(f"{_builder.data_dir}/{collection}").glob("*.md"))

    # If no source files, use content_preview (truncated but better than nothing)
    chunks = []
    if source_files:
        for f in source_files:
            text = f.read_text()
            chunks.extend(chunk_by_article(text))

    result = await _builder.summarize_long_articles(
        collection=collection,
        chunks=chunks,
        threshold=effective_threshold,
        llm_url=llm_url or None,
        llm_api_key=llm_api_key or None,
        llm_model=llm_model or None,
    )

    return {
        "status": "done",
        "collection": collection,
        "threshold": effective_threshold,
        "ai_summary_enabled": config.ai_summary_enabled if config else True,
        "articles_needing_summary": len(long_articles),
        **result,
    }
