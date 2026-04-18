"""Tests for Legifrance PISTE client (TDD)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.legifrance_client import (
    LegifranceClient,
    parse_legifrance_url,
)


class TestParseUrl:
    def test_parse_code(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/codes/texte_lc/LEGITEXT000006070158"
        )
        assert result["type"] == "code"
        assert result["id"] == "LEGITEXT000006070158"

    def test_parse_article(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000049803824"
        )
        assert result["type"] == "article"
        assert result["id"] == "LEGIARTI000049803824"

    def test_parse_loi(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000886460"
        )
        assert result["type"] == "loi"
        assert result["id"] == "JORFTEXT000000886460"

    def test_parse_jo(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000886460"
        )
        assert result["type"] == "jo"
        assert result["id"] == "JORFTEXT000000886460"

    def test_parse_unknown(self):
        result = parse_legifrance_url("https://example.com/page")
        assert result is None

    def test_parse_with_trailing_slash(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/codes/texte_lc/LEGITEXT000006070158/"
        )
        assert result["type"] == "code"
        assert result["id"] == "LEGITEXT000006070158"

    def test_parse_with_params(self):
        result = parse_legifrance_url(
            "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000049803824?dateVersion=20260101"
        )
        assert result["type"] == "article"
        assert result["id"] == "LEGIARTI000049803824"


@pytest.fixture
def client():
    return LegifranceClient(
        client_id="test-id",
        client_secret="test-secret",
    )


class TestLegifranceClient:
    def test_init(self, client):
        assert client.client_id == "test-id"

    @pytest.mark.asyncio
    async def test_get_token(self, client):
        with patch.object(client, "_post_form", new_callable=AsyncMock) as mock:
            mock.return_value = {"access_token": "tok", "expires_in": 3600}
            token = await client._get_token()
            assert token == "tok"

    @pytest.mark.asyncio
    async def test_search(self, client):
        with patch.object(client, "_api_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"results": [{"id": "LEGITEXT000006070158", "titre": "CESEDA"}]}
            results = await client.search("CESEDA")
            assert len(results["results"]) == 1

    @pytest.mark.asyncio
    async def test_get_article(self, client):
        with patch.object(client, "_api_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"article": {"id": "LEGIARTI000049803824", "texte": "..."}}
            result = await client.get_article("LEGIARTI000049803824")
            assert result["article"]["id"] == "LEGIARTI000049803824"
