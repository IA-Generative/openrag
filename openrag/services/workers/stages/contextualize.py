from __future__ import annotations

from collections import Counter
from collections.abc import MutableMapping
from typing import Any

from core.indexing.contextualize import ChunkContextualizer
from core.models.chunk import Chunk
from core.utils.exceptions import InferenceTimeoutError
from services.workers.stages._common import (
    resolve_language,
    run_with_optional_timeout,
    scrub_credentials,
    stage_timeout,
)


async def contextualize_stage(
    row: MutableMapping[str, Any],
    contextualizer: ChunkContextualizer,
    *,
    timeout: float | None = None,
    per_chunk_timeout: float = 0.0,
) -> MutableMapping[str, Any]:
    """Contextualize ``row["chunks"]`` in place."""

    try:
        chunks = row.get("chunks")
        if not _is_chunk_list(chunks):
            raise ValueError("contextualize_stage row must contain a list[Chunk] under 'chunks'")

        filename = str(row.get("filename") or "")
        language = resolve_language(row)
        # DB-resolved per-partition prompt for this file, if any; otherwise the
        # contextualizer falls back to its own (disk-loaded) default.
        system_prompt = row.get("contextualizer_prompt")
        effective_timeout = stage_timeout(timeout, len(chunks), per_item_timeout=per_chunk_timeout)
        failures: list[Exception] = []

        def record_failure(exc: Exception) -> None:
            failures.append(exc)

        row["chunks"] = await run_with_optional_timeout(
            lambda: contextualizer.contextualize(
                chunks,
                filename=filename,
                lang=language,
                system_prompt=system_prompt,
                on_failure=record_failure,
            ),
            effective_timeout,
        )
        if failures:
            row.setdefault("degraded_stages", {})["contextualize"] = str(failures[0])
        row["contextualization"] = contextualization_outcome(row["chunks"], failures)
        row["stage"] = "contextualized"
        row.pop("error", None)
        return row
    except Exception as exc:
        row["stage"] = "contextualize_failed"
        row["error"] = str(exc)
        # The pipeline indexes the file anyway, without any context (#702):
        # every chunk counts as failed.
        if _is_chunk_list(row.get("chunks")):
            row["contextualization"] = contextualization_outcome(row["chunks"], [exc], all_failed=True)
        raise
    finally:
        scrub_credentials(row)


def contextualization_outcome(
    chunks: list[Chunk],
    failures: list[Exception],
    *,
    all_failed: bool = False,
) -> dict[str, Any]:
    """How many chunks got a context, for the task status and the file catalog.

    ``failed`` is read from the chunks themselves rather than from the failure
    count: a whole-document fallback reports one failure but leaves every chunk
    without context. ``errors`` counts the failed LLM calls by cause, so a
    client can tell a quota problem (``rate_limited``) from a broken endpoint.
    """
    total = len(chunks)
    failed = total if all_failed else sum(1 for chunk in chunks if not (chunk.context or "").strip())
    return {
        "total": total,
        "failed": failed,
        "errors": dict(Counter(_failure_cause(exc) for exc in failures)),
    }


def _failure_cause(exc: BaseException) -> str:
    if getattr(exc, "status_code", None) == 429:
        return "rate_limited"
    if isinstance(exc, (TimeoutError, InferenceTimeoutError)):
        return "timeout"
    if isinstance(exc, ValueError) and "empty" in str(exc):
        return "empty_response"
    return "other"


def _is_chunk_list(value: Any) -> bool:
    """Return whether ``value`` is a concrete list of domain chunks."""
    return isinstance(value, list) and all(isinstance(chunk, Chunk) for chunk in value)
