"""Legifrance PISTE API client for MyRAG."""

import re
import time

import httpx

from app.config import settings

# URL patterns for parsing Legifrance URLs
_URL_PATTERNS = [
    (re.compile(r"legifrance\.gouv\.fr/codes/texte_lc/(LEGITEXT\d+)"), "code"),
    (re.compile(r"legifrance\.gouv\.fr/codes/article_lc/(LEGIARTI\d+)"), "article"),
    (re.compile(r"legifrance\.gouv\.fr/loda/id/(JORFTEXT\d+|LEGITEXT\d+)"), "loi"),
    (re.compile(r"legifrance\.gouv\.fr/jorf/id/(JORFTEXT\d+)"), "jo"),
]


def parse_legifrance_url(url: str) -> dict | None:
    """Parse a Legifrance URL and extract type + ID."""
    for pattern, doc_type in _URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return {"type": doc_type, "id": match.group(1), "url": url}
    return None


class LegifranceClient:
    """Client for the Legifrance PISTE API."""

    PISTE_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
    PISTE_API_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 30.0,
    ):
        self.client_id = client_id or settings.legifrance_client_id
        self.client_secret = client_secret or settings.legifrance_client_secret
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires: float = 0

    async def _post_form(self, url: str, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token

        result = await self._post_form(self.PISTE_TOKEN_URL, {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "openid",
        })
        self._token = result["access_token"]
        self._token_expires = time.time() + result.get("expires_in", 3600) - 60
        return self._token

    async def _api_headers(self) -> dict:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _api_post(self, path: str, json: dict) -> dict:
        headers = await self._api_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.PISTE_API_URL}{path}",
                headers=headers,
                json=json,
            )
            resp.raise_for_status()
            return resp.json()

    async def _api_get(self, path: str, params: dict | None = None) -> dict:
        headers = await self._api_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.PISTE_API_URL}{path}",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    # --- Public API ---

    async def search(self, query: str, fond: str = "CODE_DATE", page_size: int = 10) -> dict:
        """Search Legifrance by text query."""
        return await self._api_post("/search", {
            "fond": fond,
            "recherche": {
                "champs": [{"typeChamp": "ALL", "criteres": [{"typeRecherche": "EXACTE", "valeur": query}]}],
                "pageNumber": 1,
                "pageSize": page_size,
            },
        })

    async def get_article(self, article_id: str) -> dict:
        """Get a single article by LEGIARTI ID."""
        return await self._api_post("/consult/getArticle", {"id": article_id})

    async def get_code_toc(self, code_id: str) -> dict:
        """Get table of contents for a code."""
        return await self._api_post("/consult/code/tableMatieres", {
            "textId": code_id,
            "date": time.strftime("%Y-%m-%d"),
        })

    async def get_article_by_num(self, code_id: str, article_num: str) -> dict:
        """Get an article by code ID and article number (e.g., L421-1)."""
        return await self._api_post("/consult/getArticleByNum", {
            "textId": code_id,
            "articleNum": article_num,
        })

    def is_configured(self) -> bool:
        """Check if PISTE credentials are configured."""
        return bool(self.client_id and self.client_secret)
