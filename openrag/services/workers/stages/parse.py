from __future__ import annotations

import asyncio
from collections.abc import MutableMapping
from typing import Any

from core.indexing.parsers.document_parser import DocumentParser
from core.models.document import Document, ProcessedDocument
from services.workers.stages._common import scrub_credentials


async def parse_stage(
    row: MutableMapping[str, Any],
    parser: DocumentParser,
    *,
    timeout: float | None = None,
) -> MutableMapping[str, Any]:
    """Parse ``row["document"]`` and mutate the row with the stage result."""

    try:
        document = row.get("document")
        if not isinstance(document, Document):
            raise ValueError("parse_stage row must contain a Document under 'document'")

        processed = await _parse_with_timeout(parser, document, timeout)
        row["processed_document"] = processed
        if processed.parse_info:
            row["parse"] = dict(processed.parse_info)
        sheet_info = processed.parse_info.get("spreadsheet") or {}
        if sheet_info.get("truncated"):
            row.setdefault("degraded_stages", {})["parse"] = (
                f"spreadsheet truncated: kept {sheet_info.get('rows_kept')} of {sheet_info.get('rows_total')} rows"
            )
        failed_pages = processed.parse_info.get("failed_pages") or 0
        if failed_pages:
            pages = processed.parse_info.get("pages") or processed.page_count
            row.setdefault("degraded_stages", {})["parse"] = f"OCR lost {failed_pages}/{pages} pages"
        row["stage"] = "parsed"
        row.pop("error", None)
        return row
    except Exception as exc:
        row["stage"] = "parse_failed"
        row["error"] = str(exc)
        raise
    finally:
        scrub_credentials(row)


async def _parse_with_timeout(
    parser: DocumentParser,
    document: Document,
    timeout: float | None,
) -> ProcessedDocument:
    deadline = asyncio.timeout(timeout)  # timeout=None never expires
    try:
        async with deadline:
            return await parser.parse(document)
    except TimeoutError as exc:
        if not deadline.expired():
            # The parser's own bound (a pool deadline, a Marker child's limit)
            # fired, not ours, and its message already names it. Relabeling it
            # would hide that cause behind a bound that never expired.
            raise
        # The bare TimeoutError from our deadline has an empty str(); give the
        # failed-file report (row["error"]) a message that names the file and
        # the bound that was exceeded.
        raise TimeoutError(f"parse timed out after {timeout:g}s for {document.filename!r}") from exc
