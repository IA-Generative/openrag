"""
title: MyRAG Collection Filter
description: Detecte #collection dans le prompt et injecte le contexte RAG depuis OpenRAG
version: 0.1.0
"""

import re

import requests
from pydantic import BaseModel, Field


class Pipeline:
    class Valves(BaseModel):
        openrag_url: str = Field(
            default="http://openrag:8080",
            description="URL du service OpenRAG",
        )
        openrag_token: str = Field(
            default="",
            description="Token admin OpenRAG",
        )
        myrag_url: str = Field(
            default="http://myrag:8200",
            description="URL du service MyRAG (pour le system prompt)",
        )
        top_k: int = Field(default=5, description="Nombre de chunks a recuperer")
        enabled: bool = Field(default=True, description="Activer le filtre")

    def __init__(self):
        self.type = "filter"
        self.id = "myrag-collection-filter"
        self.name = "MyRAG #Collection Filter"
        self.valves = self.Valves()

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    def inlet(self, body: dict, __user__: dict | None = None) -> dict:
        """Intercept messages BEFORE the LLM. Detect #collection and inject RAG context."""
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return body

        content = last_msg.get("content", "")

        # Detect #collection pattern
        match = re.search(r"#(\S+)", content)
        if not match:
            return body

        collection = match.group(1)
        question = re.sub(r"#\S+\s*", "", content).strip()

        if not question:
            return body

        # Search OpenRAG
        try:
            resp = requests.get(
                f"{self.valves.openrag_url}/search",
                params={
                    "text": question,
                    "partitions": collection,
                    "top_k": self.valves.top_k,
                },
                headers={"Authorization": f"Bearer {self.valves.openrag_token}"},
                timeout=30,
            )
            if not resp.ok:
                return body

            documents = resp.json().get("documents", [])
        except Exception:
            return body

        if not documents:
            return body

        # Format context
        context_parts = [f"[Source {i+1}] {doc.get('metadata', {}).get('filename', 'unknown')}:\n{doc.get('content', '')[:500]}"
                         for i, doc in enumerate(documents[:self.valves.top_k])]
        context = "\n\n---\n\n".join(context_parts)

        # Get collection system prompt
        system_prompt = ""
        try:
            resp = requests.get(
                f"{self.valves.myrag_url}/api/collections/{collection}/system-prompt",
                timeout=5,
            )
            if resp.ok:
                system_prompt = resp.json().get("system_prompt", "")
        except Exception:
            pass

        # Inject system prompt if available
        if system_prompt:
            # Add or replace system message
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = system_prompt
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

        # Replace user message with context-enriched version
        last_msg["content"] = f"""Contexte (collection: {collection}):

{context}

---

Question: {question}"""

        body["messages"] = messages
        return body
