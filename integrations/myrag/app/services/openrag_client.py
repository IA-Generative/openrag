"""OpenRAG API client for MyRAG."""

import io
import uuid

import httpx

from app.config import settings


class OpenRAGClient:
    def __init__(
        self,
        base_url: str | None = None,
        admin_token: str | None = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or settings.openrag_url).rstrip("/")
        self.admin_token = admin_token or settings.openrag_admin_token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json,
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    async def _upload_file(
        self, path: str, file_content: bytes, filename: str, metadata: dict | None = None
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            files = {"file": (filename, io.BytesIO(file_content), "text/markdown")}
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=headers,
                files=files,
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    # --- Public API ---

    async def create_partition(self, name: str) -> dict:
        try:
            return await self._post(f"/partition/{name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return {"status": "exists"}
            raise

    async def upload_chunk(self, partition: str, chunk: dict) -> dict:
        file_id = str(uuid.uuid4())
        content = chunk["content"].encode("utf-8")
        filename = chunk.get("filename", f"chunk-{file_id}.md")
        return await self._upload_file(
            f"/indexer/partition/{partition}/file/{file_id}",
            file_content=content,
            filename=filename,
        )

    async def upload_chunks(self, partition: str, chunks: list[dict]) -> list[dict]:
        results = []
        for chunk in chunks:
            result = await self.upload_chunk(partition, chunk)
            results.append(result)
        return results

    async def search(
        self, partition: str, query: str, top_k: int = 5
    ) -> dict:
        return await self._get(
            "/search",
            params={"text": query, "partitions": partition, "top_k": top_k},
        )

    async def list_models(self) -> dict:
        return await self._get("/v1/models")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health_check")
                return resp.status_code == 200
        except Exception:
            return False
