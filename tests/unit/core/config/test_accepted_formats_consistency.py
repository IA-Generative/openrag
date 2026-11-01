"""Every extension the config maps a mimetype to must also be an accepted upload extension.

The upload check accepts a file by extension (``loader.file_loaders`` keys) or by
the ``mimetype`` in its metadata (``loader.mimetypes``). A format added to one
list only is half-supported: openrag#15 added the spreadsheet mimetypes but not
the extensions, so a ``.xlsx`` uploaded without a mimetype got a 415; v2.3.3
did the same for ``text/csv``, in the model defaults only.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from core.config.indexation import FileLoadersConfig, MimetypesConfig
from core.models.document import Document, DocumentType

CONFIG = Path(__file__).resolve().parents[4] / "conf" / "config.yaml"


def _loader_section() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["loader"]


def test_mimetype_extensions_are_accepted_upload_extensions():
    loader = _loader_section()
    mimetype_extensions = {ext.lstrip(".") for ext in loader["mimetypes"].values()}
    accepted = set(loader["file_loaders"])
    assert mimetype_extensions <= accepted, sorted(mimetype_extensions - accepted)


def test_default_mimetype_extensions_are_default_upload_extensions():
    mimetype_extensions = {ext.lstrip(".") for ext in MimetypesConfig().to_dict().values()}
    accepted = set(FileLoadersConfig().model_dump())
    assert mimetype_extensions <= accepted, sorted(mimetype_extensions - accepted)


def test_csv_is_accepted_on_its_extension():
    assert "csv" in FileLoadersConfig().model_dump()
    assert "csv" in _loader_section()["file_loaders"]
    assert _loader_section()["mimetypes"]["text/csv"] == ".csv"
    assert Document.detect_content_type("communes.csv") is DocumentType.CSV


def test_spreadsheet_extensions_are_accepted_by_default_and_in_the_shipped_config():
    for ext in ("xlsx", "xlsm", "xls", "ods"):
        assert ext in FileLoadersConfig().model_dump()
        assert ext in _loader_section()["file_loaders"]
        assert Document.detect_content_type(f"a.{ext}") is DocumentType.SPREADSHEET
