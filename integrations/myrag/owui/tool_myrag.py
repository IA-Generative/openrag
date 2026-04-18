"""
title: MyRAG (beta)
description: Recherche RAG + graph de references dans les collections MyRAG
version: 0.1.0
"""

import json
import re

import requests
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse


class Tools:
    class Valves(BaseModel):
        myrag_url: str = Field(
            default="http://myrag:8200",
            description="URL du service MyRAG",
        )
        openrag_url: str = Field(
            default="http://openrag:8080",
            description="URL du service OpenRAG",
        )
        openrag_token: str = Field(
            default="",
            description="Token admin OpenRAG",
        )
        default_collection: str = Field(
            default="ceseda-v3",
            description="Collection par defaut",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _openrag_headers(self):
        return {"Authorization": f"Bearer {self.valves.openrag_token}"}

    def _search_openrag(self, collection: str, query: str, top_k: int = 5) -> list[dict]:
        """Search OpenRAG and return documents."""
        try:
            resp = requests.get(
                f"{self.valves.openrag_url}/search",
                params={"text": query, "partitions": collection, "top_k": top_k},
                headers=self._openrag_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("documents", [])
        except Exception:
            return []

    def _get_graph_related(self, collection: str, article_id: str) -> dict:
        """Get related articles from MyRAG graph."""
        try:
            resp = requests.get(
                f"{self.valves.myrag_url}/graph/{collection}/related",
                params={"article": article_id, "depth": 1},
                timeout=10,
            )
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return {"nodes": [], "edges": []}

    def _get_article(self, collection: str, article_id: str) -> dict:
        """Get article data from MyRAG."""
        try:
            resp = requests.get(
                f"{self.valves.myrag_url}/articles/{collection}/{article_id}/json",
                timeout=10,
            )
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return {}

    def _extract_article_ids(self, text: str) -> list[str]:
        """Extract article IDs from response text."""
        return re.findall(r"\b([LRD]\d+(?:-\d+)*)\b", text)

    def _render_sources_html(self, docs: list[dict], graph_edges: list[dict] = None, collection: str = "") -> str:
        """Render sources + mini graph as HTML for iframe."""
        myrag = self.valves.myrag_url

        sources_html = ""
        for i, doc in enumerate(docs[:5]):
            meta = doc.get("metadata", {})
            filename = meta.get("filename", "")
            article = filename.replace("Article-", "").replace("Article_", "").replace(".md", "")
            content = doc.get("content", "")[:200].replace("<", "&lt;")
            link = f"{myrag}/articles/{collection}/{article}" if article else "#"

            sources_html += f"""
            <div style="border:1px solid #e5e5e5;border-radius:4px;padding:8px;margin:4px 0;">
                <a href="{link}" target="_blank" style="color:#000091;font-weight:bold;text-decoration:none;">
                    {filename or f'Source {i+1}'}
                </a>
                <p style="font-size:0.8rem;color:#666;margin:4px 0 0 0;">{content}...</p>
            </div>"""

        graph_html = ""
        if graph_edges:
            graph_html = '<div style="margin-top:12px;border-top:1px solid #e5e5e5;padding-top:8px;">'
            graph_html += '<strong style="font-size:0.85rem;">🔗 References croisees</strong><br>'
            for edge in graph_edges[:10]:
                graph_html += f'<span style="font-size:0.8rem;">{edge["source"]} → {edge["target"]}</span><br>'
            graph_html += f'<a href="{myrag}/graph?corpus_id={collection}" target="_blank" '
            graph_html += 'style="font-size:0.8rem;color:#000091;">📊 Voir le graph complet</a></div>'

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, sans-serif; padding: 12px; margin: 0; }}
</style>
<script>
const ro = new ResizeObserver(()=>{{
    window.parent.postMessage({{type:'iframe-resize',height:document.documentElement.scrollHeight}},'*');
}});
ro.observe(document.body);
</script>
</head><body>
<strong>📄 Sources utilisees</strong>
{sources_html}
{graph_html}
</body></html>"""

    async def search_collection(
        self,
        question: str,
        collection: str = "",
        __user__: dict = {},
    ) -> tuple:
        """Rechercher dans une collection MyRAG. Retourne les articles pertinents avec le graph de references.

        :param question: La question a poser
        :param collection: Nom de la collection (defaut: collection configuree)
        """
        col = collection or self.valves.default_collection

        # Search
        docs = self._search_openrag(col, question)

        # Get graph for cited articles
        graph_edges = []
        for doc in docs[:3]:
            article = doc.get("metadata", {}).get("filename", "").replace("Article-", "").replace("Article_", "").replace(".md", "")
            if article:
                related = self._get_graph_related(col, article)
                graph_edges.extend(related.get("edges", []))

        # Render HTML
        html = self._render_sources_html(docs, graph_edges, col)

        # Context for LLM
        context = {
            "sources": [
                {
                    "article": d.get("metadata", {}).get("filename", ""),
                    "text": d.get("content", "")[:500],
                }
                for d in docs[:5]
            ],
            "graph_links": graph_edges[:10],
            "_instructions": "Cite les articles par leur numero (ex: article L423-1). Indique le Livre, Titre et Chapitre.",
        }

        return (
            HTMLResponse(content=html, headers={"Content-Disposition": "inline"}),
            context,
        )

    async def view_article(
        self,
        collection: str,
        article_id: str,
        __user__: dict = {},
    ) -> tuple:
        """Afficher un article complet avec ses references.

        :param collection: Nom de la collection
        :param article_id: Identifiant de l'article (ex: L421-1)
        """
        myrag = self.valves.myrag_url

        # Get article HTML from MyRAG
        try:
            resp = requests.get(f"{myrag}/articles/{collection}/{article_id}", timeout=10)
            if resp.ok:
                html = resp.text
            else:
                html = f"<html><body><p>Article {article_id} non trouve.</p></body></html>"
        except Exception:
            html = f"<html><body><p>Erreur de connexion a MyRAG.</p></body></html>"

        # Get article data for LLM context
        article = self._get_article(collection, article_id)

        context = {
            "article": article_id,
            "content": article.get("content", "")[:2000],
            "references": article.get("references", []),
            "_instructions": f"L'utilisateur consulte l'article {article_id}. Resume-le et mentionne les articles lies.",
        }

        return (
            HTMLResponse(content=html, headers={"Content-Disposition": "inline"}),
            context,
        )

    async def explore_graph(
        self,
        collection: str = "",
        focus_article: str = "",
        __user__: dict = {},
    ) -> tuple:
        """Visualiser le graph de references interactif (Cytoscape.js).

        :param collection: Nom de la collection
        :param focus_article: Article central du graph (optionnel)
        """
        col = collection or self.valves.default_collection
        myrag = self.valves.myrag_url
        graph_url = f"{myrag}/graph?corpus_id={col}"
        if focus_article:
            graph_url += f"&query={focus_article}"

        html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;height:80vh">
<iframe src="{graph_url}" style="width:100%;height:100%;border:none"></iframe>
<script>
const ro = new ResizeObserver(()=>{{
    window.parent.postMessage({{type:'iframe-resize',height:document.documentElement.scrollHeight}},'*');
}});
ro.observe(document.body);
</script>
</body></html>"""

        context = {
            "collection": col,
            "focus": focus_article,
            "_instructions": "Le graph interactif est affiche. L'utilisateur peut cliquer sur les noeuds pour explorer les relations entre articles.",
        }

        return (
            HTMLResponse(content=html, headers={"Content-Disposition": "inline"}),
            context,
        )

    async def browse_collection(
        self,
        collection: str = "",
        __user__: dict = {},
    ) -> tuple:
        """Naviguer dans la table des matieres d'une collection.

        :param collection: Nom de la collection
        """
        col = collection or self.valves.default_collection
        myrag = self.valves.myrag_url

        # Get graph data to build ToC
        try:
            resp = requests.get(
                f"{myrag}/graph/data",
                params={"corpus_id": col, "max_nodes": 500},
                timeout=10,
            )
            data = resp.json() if resp.ok else {"nodes": []}
        except Exception:
            data = {"nodes": []}

        # Group by Livre
        by_livre = {}
        for node in data.get("nodes", []):
            livre = node.get("source_group", "other")
            by_livre.setdefault(livre, []).append(node)

        toc_html = ""
        for livre, nodes in sorted(by_livre.items()):
            toc_html += f'<h3 style="color:#000091;margin:12px 0 4px 0;">{livre}</h3>'
            for n in sorted(nodes, key=lambda x: x["id"]):
                link = f"{myrag}/articles/{col}/{n['id']}"
                toc_html += f'<a href="{link}" target="_blank" style="display:block;padding:2px 8px;font-size:0.85rem;color:#161616;text-decoration:none;">{n["label"]}</a>'

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body {{ font-family: -apple-system, sans-serif; padding: 12px; }}</style>
<script>
const ro = new ResizeObserver(()=>{{
    window.parent.postMessage({{type:'iframe-resize',height:document.documentElement.scrollHeight}},'*');
}});
ro.observe(document.body);
</script>
</head><body>
<h2>📋 Table des matieres — {col}</h2>
<p style="color:#666;font-size:0.85rem;">{len(data.get('nodes',[]))} articles</p>
{toc_html}
<div style="margin-top:16px;">
<a href="{myrag}/graph?corpus_id={col}" target="_blank" style="color:#000091;">📊 Voir le graph</a>
</div>
</body></html>"""

        context = {
            "collection": col,
            "total_articles": len(data.get("nodes", [])),
            "_instructions": "L'utilisateur consulte la table des matieres. Propose-lui de poser une question sur un article specifique.",
        }

        return (
            HTMLResponse(content=html, headers={"Content-Disposition": "inline"}),
            context,
        )
