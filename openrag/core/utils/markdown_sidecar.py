"""Where the ``SAVE_MARKDOWN`` copy of an upload lives, and whether it may be touched.

Shared by the indexing pipeline (which writes it), the file route that serves
it and the delete path that removes it, so all three agree on one path.
"""

from __future__ import annotations

from pathlib import Path


def markdown_sidecar_path(source_path: str | Path) -> Path:
    """Path of the ``SAVE_MARKDOWN`` copy for an upload stored at ``source_path``.

    The suffix is appended rather than swapped so a markdown upload is never
    overwritten.
    """
    return Path(f"{source_path}.md")


def sidecar_in_data_dir(source_path: str | Path | None, data_dir: str | Path | None) -> Path | None:
    """The sidecar of ``source_path``, or ``None`` when it is not under ``data_dir``.

    ``source`` comes from catalog metadata; the pipeline only ever writes a
    sidecar under the data directory, so anything else is never read or deleted.
    """
    if not source_path or data_dir is None:
        return None
    sidecar = markdown_sidecar_path(source_path)
    if not sidecar.resolve().is_relative_to(Path(data_dir).resolve()):
        return None
    return sidecar
