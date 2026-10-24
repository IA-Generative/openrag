"""DotsOCR VLM PDF client: page accounting (mycollections#152)."""

from __future__ import annotations

import json

import pytest
from core.models.document import Document, DocumentType
from PIL import Image
from services.inference.parsers.dotsocr import DotsOCRPdfClient

_PAGE = json.dumps([{"bbox": [0, 0, 10, 10], "category": "Text", "text": "Bonjour"}])


class _ScriptedVLM:
    """Answers each caption call with the next scripted reply (an Exception is raised)."""

    def __init__(self, replies: list[object]) -> None:
        self.replies = list(replies)

    async def caption_image(self, image_bytes: bytes, prompt: str | None = None) -> str:
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply  # type: ignore[return-value]


def _client(replies: list[object], pages: int, monkeypatch: pytest.MonkeyPatch) -> DotsOCRPdfClient:
    client = DotsOCRPdfClient(_ScriptedVLM(replies), concurrency_limit=1)
    monkeypatch.setattr(
        DotsOCRPdfClient, "_render_pdf_pages", staticmethod(lambda raw, scale: [Image.new("RGB", (8, 8))] * pages)
    )
    return client


def _pdf() -> Document:
    return Document(id="d1", filename="scan.pdf", content_type=DocumentType.PDF, raw_bytes=b"%PDF-1.4")


@pytest.mark.asyncio
async def test_all_pages_read(monkeypatch: pytest.MonkeyPatch) -> None:
    processed = await _client([_PAGE, _PAGE], 2, monkeypatch).parse(_pdf())

    assert processed.parse_info == {"pages": 2, "failed_pages": 0}
    assert [b.text for b in processed.text_blocks] == ["Bonjour", "Bonjour"]


@pytest.mark.asyncio
async def test_a_failed_or_off_schema_page_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [_PAGE, RuntimeError("LLM error (429)"), "this is not the layout JSON"]

    processed = await _client(replies, 3, monkeypatch).parse(_pdf())

    assert processed.parse_info == {"pages": 3, "failed_pages": 2}
    assert len(processed.text_blocks) == 1


@pytest.mark.asyncio
async def test_every_page_failing_fails_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [RuntimeError("LLM error (429)"), RuntimeError("LLM error (429)")]

    with pytest.raises(RuntimeError, match="every page"):
        await _client(replies, 2, monkeypatch).parse(_pdf())
