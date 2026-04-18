"""Graph builder — construct article reference graphs from chunks."""

import json
import math
import re
from pathlib import Path

import networkx as nx

ARTICLE_REF_RE = re.compile(
    r"\b[Ll](?:'article|'article)\s+([LRD])\.\s?(\d+(?:-\d+)*)\b"
    r"|\b([LRD])\.\s?(\d+(?:-\d+)*)\b"
)


def extract_references(text: str) -> list[str]:
    """Extract article references from text."""
    refs = set()
    for match in ARTICLE_REF_RE.finditer(text):
        prefix = match.group(1) or match.group(3)
        number = match.group(2) or match.group(4)
        if prefix and number:
            refs.add(f"{prefix}{number}")
    return sorted(refs)


def build_graph_from_chunks(chunks: list[dict]) -> nx.DiGraph:
    """Build a directed graph from chunks with reference metadata."""
    graph = nx.DiGraph()

    # Index all article IDs
    article_ids = set()
    for chunk in chunks:
        article = chunk.get("metadata", {}).get("article")
        if article:
            article_ids.add(article)

    # Add nodes
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        article = meta.get("article")
        if not article:
            continue

        graph.add_node(
            article,
            label=f"Article {article}",
            entity_type="article",
            livre=meta.get("livre", ""),
            titre=meta.get("titre", ""),
            chapitre=meta.get("chapitre", ""),
            parent_path=meta.get("parent_path", ""),
            source_group=f"{meta.get('livre', '')}",
            content_preview=chunk.get("content", "")[:500],  # short brut (no LLM)
            content_full_length=len(chunk.get("content", "")),
            ai_summary="",  # populated by summarize_long_articles() if LLM enabled
            filename=chunk.get("filename", ""),
            referenced_by=[],
        )

    # Add edges from references
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        article = meta.get("article")
        if not article:
            continue

        references = meta.get("references", [])
        for ref in references:
            # Only add edge if target exists in our graph
            if ref in article_ids and ref != article:
                graph.add_edge(
                    article,
                    ref,
                    description="cite",
                    weight=1.0,
                )

                # Track referenced_by on target node
                if ref in graph.nodes:
                    rb = graph.nodes[ref].get("referenced_by", [])
                    if article not in rb:
                        rb.append(article)
                        graph.nodes[ref]["referenced_by"] = rb

    return graph


class GraphBuilder:
    """Manages graphs per collection with persistence."""

    def __init__(self, data_dir: str | None = None):
        from app.config import settings
        self.data_dir = data_dir or settings.data_dir
        self._graphs: dict[str, nx.DiGraph] = {}

    def build(self, collection: str, chunks: list[dict]) -> nx.DiGraph:
        """Build a graph from chunks and store in memory."""
        graph = build_graph_from_chunks(chunks)
        self._graphs[collection] = graph
        return graph

    def get(self, collection: str) -> nx.DiGraph | None:
        """Get a graph from memory, or try to load from disk."""
        if collection not in self._graphs:
            loaded = self.load(collection)
            if loaded:
                self._graphs[collection] = loaded
        return self._graphs.get(collection)

    def save(self, collection: str):
        """Save a graph to disk as JSON."""
        graph = self._graphs.get(collection)
        if not graph:
            return

        path = Path(self.data_dir) / collection / "graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "nodes": [],
            "edges": [],
        }

        for node_id, attrs in graph.nodes(data=True):
            data["nodes"].append({"id": node_id, **attrs})

        for source, target, attrs in graph.edges(data=True):
            data["edges"].append({"source": source, "target": target, **attrs})

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load(self, collection: str) -> nx.DiGraph | None:
        """Load a graph from disk."""
        path = Path(self.data_dir) / collection / "graph.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        graph = nx.DiGraph()

        for node in data.get("nodes", []):
            node_id = node.pop("id")
            graph.add_node(node_id, **node)

        for edge in data.get("edges", []):
            source = edge.pop("source")
            target = edge.pop("target")
            graph.add_edge(source, target, **edge)

        self._graphs[collection] = graph
        return graph

    def get_subgraph(
        self, collection: str, article_ids: list[str], depth: int = 1
    ) -> nx.DiGraph | None:
        """Get a subgraph centered on given articles, expanding N hops."""
        graph = self.get(collection)
        if not graph:
            return None

        nodes_to_include = set()
        frontier = set(a for a in article_ids if a in graph.nodes)

        for _ in range(depth + 1):
            nodes_to_include.update(frontier)
            next_frontier = set()
            for node in frontier:
                next_frontier.update(graph.successors(node))
                next_frontier.update(graph.predecessors(node))
            frontier = next_frontier - nodes_to_include

        return graph.subgraph(nodes_to_include).copy()

    async def summarize_long_articles(
        self,
        collection: str,
        chunks: list[dict],
        threshold: int = 1000,
        llm_url: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> dict:
        """Generate AI summaries for articles longer than threshold.

        Requires LLM access (Scaleway, OpenAI-compatible).
        Stores summaries in graph nodes as ai_summary field.
        """
        import httpx
        from app.config import settings

        graph = self.get(collection)
        if not graph:
            return {"summarized": 0, "skipped": 0, "errors": 0}

        url = llm_url or settings.openrag_url.replace(":8080", "")  # fallback
        # Use the configured LLM from .env if available
        base_url = llm_url or "https://api.scaleway.ai/v1"
        api_key = llm_api_key or ""
        model = llm_model or "mistral-small-3.2-24b-instruct-2506"

        # Index chunks by article for full content
        chunk_by_article = {}
        for chunk in chunks:
            article = chunk.get("metadata", {}).get("article")
            if article:
                chunk_by_article[article] = chunk.get("content", "")

        summarized = 0
        skipped = 0
        errors = 0

        async with httpx.AsyncClient(timeout=60) as client:
            for node_id in graph.nodes:
                full_text = chunk_by_article.get(node_id, "")
                if len(full_text) < threshold:
                    skipped += 1
                    continue

                try:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "Tu es un assistant juridique. Resume l'article suivant en 3-5 phrases. Conserve les numeros d'articles cites. Commence par 'Cet article...'",
                                },
                                {"role": "user", "content": full_text[:8000]},
                            ],
                            "max_tokens": 300,
                            "temperature": 0.1,
                        },
                    )
                    if resp.status_code == 200:
                        summary = resp.json()["choices"][0]["message"]["content"]
                        graph.nodes[node_id]["ai_summary"] = summary
                        summarized += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        # Save updated graph
        self.save(collection)

        return {"summarized": summarized, "skipped": skipped, "errors": errors}

    def to_graph_data_response(
        self,
        collection: str,
        query: str = "",
        max_nodes: int = 80,
        min_weight: float = 0.0,
    ) -> dict:
        """Convert graph to GraphDataResponse format (compatible with grafragexp viewer)."""
        graph = self.get(collection)
        if not graph:
            return {
                "graph_ready": False,
                "graph_kind": "article",
                "corpus_id": collection,
                "nodes": [],
                "edges": [],
                "total_nodes": 0,
                "total_edges": 0,
                "message": "No graph available for this collection",
            }

        # Filter by query if provided
        if query:
            # Find nodes matching query
            matching = [
                n for n, d in graph.nodes(data=True)
                if query.lower() in n.lower()
                or query.lower() in d.get("content_preview", "").lower()
                or query.lower() in d.get("label", "").lower()
            ]
            if matching:
                subgraph = self.get_subgraph(collection, matching, depth=1)
                if subgraph:
                    graph = subgraph

        # Limit nodes
        if graph.number_of_nodes() > max_nodes:
            # Keep nodes with highest degree
            sorted_nodes = sorted(
                graph.nodes, key=lambda n: graph.degree(n), reverse=True
            )[:max_nodes]
            graph = graph.subgraph(sorted_nodes).copy()

        nodes = []
        for node_id, attrs in graph.nodes(data=True):
            degree = graph.degree(node_id)
            size = max(8, min(32, degree * 4 + 8))
            livre = attrs.get("livre", "")

            # Use AI summary if available, otherwise raw preview
            ai_summary = attrs.get("ai_summary", "")
            preview = attrs.get("content_preview", "")
            full_length = attrs.get("content_full_length", 0)

            if ai_summary:
                description = f"🤖 Resume IA :\n{ai_summary}"
                fragment_text = f"🤖 Resume par l'IA (article original : {full_length} caracteres)\n\n{ai_summary}"
            else:
                description = preview
                fragment_text = preview
                if full_length > 500:
                    fragment_text += f"\n\n[... tronque — {full_length} caracteres au total]"

            nodes.append({
                "id": node_id,
                "label": attrs.get("label", node_id),
                "entity_type": attrs.get("entity_type", "article"),
                "description": description,
                "degree": degree,
                "frequency": 1,
                "size": size,
                "source_group": f"Livre-{livre}" if livre else "other",
                "document_paths": [attrs.get("filename", "")],
                "fragments": [{
                    "id": f"{node_id}:preview",
                    "text": fragment_text,
                    "token_count": 0,
                    "document_paths": [attrs.get("filename", "")],
                }] if preview or ai_summary else [],
            })

        edges = []
        for source, target, attrs in graph.edges(data=True):
            weight = attrs.get("weight", 1.0)
            if weight < min_weight:
                continue
            edges.append({
                "source": source,
                "target": target,
                "description": attrs.get("description", "cite"),
                "weight": weight,
                "document_paths": [],
                "fragments": [],
            })

        return {
            "graph_ready": True,
            "graph_kind": "article",
            "corpus_id": collection,
            "query": query,
            "max_nodes": max_nodes,
            "min_weight": min_weight,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes,
            "edges": edges,
            "message": "",
            "available_sources": sorted(set(
                n.get("source_group", "") for n in nodes
            )),
        }
