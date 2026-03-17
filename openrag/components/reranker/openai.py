import asyncio

import httpx
from langchain_core.documents.base import Document
from utils.logger import get_logger

from .base import BaseReranker

logger = get_logger()


class OpenAIReranker(BaseReranker):
    def __init__(self, config):
        self.model_name = config.reranker["model_name"]
        self.api_key = config.reranker["api_key"]
        base_url = config.reranker.get("base_url", "").rstrip("/")
        self.rerank_url = f"{base_url}/rerank"
        semaphore = config.reranker.get("semaphore", 40)
        self.semaphore = asyncio.Semaphore(semaphore)
        logger.debug("OpenAI Reranker initialized", model_name=self.model_name)

    async def rerank(self, query: str, documents: list[Document], top_k: int | None = None) -> list[Document]:
        async with self.semaphore:
            logger.debug("Reranking documents", documents_count=len(documents), top_k=top_k)
            top_k = min(top_k, len(documents)) if top_k is not None else len(documents)
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.rerank_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model_name,
                            "query": query,
                            "documents": [doc.page_content for doc in documents],
                            "top_n": top_k,
                        },
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                output = []
                for result in data["results"]:
                    doc = documents[result["index"]]
                    doc.metadata["relevance_score"] = result["relevance_score"]
                    output.append(doc)
                return output

            except Exception as e:
                logger.error(
                    "Reranking failed",
                    error=str(e),
                    model_name=self.model_name,
                    documents_count=len(documents),
                )
                return documents[:top_k]
