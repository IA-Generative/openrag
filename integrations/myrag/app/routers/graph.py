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
