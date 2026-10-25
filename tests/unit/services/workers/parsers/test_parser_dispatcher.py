"""Unit tests for the content-type → parser dispatch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core.models.document import Document, DocumentType, ProcessedDocument, TextBlock
from services.workers.parsers.parser_dispatcher import (
    ParserDispatcher,
    build_caption_vlm,
)


def _config(
    *,
    pdf="MarkerLoader",
    audio="LocalWhisperLoader",
    image_captioning=True,
    vlm_base_url="",
    vlm_enable_thinking=None,
    openai_loader_enable_thinking=None,
) -> SimpleNamespace:
    file_loaders = SimpleNamespace(
        pdf=pdf,
        mp3=audio,
        wav=audio,
        flac=audio,
        mp4=audio,
    )
    openai = SimpleNamespace(
        base_url="http://openai:8000/v1",
        model="dotsocr-model",
        api_key="k",
        timeout=60,
        concurrency_limit=20,
        enable_thinking=openai_loader_enable_thinking,
    )
    transcriber = SimpleNamespace(
        base_url="http://transcriber:8000/v1",
        api_key="k",
        model_name="asr-model",
        timeout=60,
        direct_upload_suffixes={".mp3", ".wav"},
        use_whisper_lang_detector=False,
        max_concurrent_chunks=1,
    )
    loader = SimpleNamespace(
        file_loaders=file_loaders,
        image_captioning=image_captioning,
        openai=openai,
        transcriber=transcriber,
    )
    vlm = SimpleNamespace(
        base_url=vlm_base_url,
        model="m",
        api_key="k",
        timeout=60,
        enable_thinking=vlm_enable_thinking,
    )
    return SimpleNamespace(loader=loader, vlm=vlm)


class _FakeParser:
    def __init__(self) -> None:
        self.seen: Document | None = None

    def supported_types(self) -> list[str]:
        return []

    async def parse(self, document: Document) -> ProcessedDocument:
        self.seen = document
        return ProcessedDocument(document_id=document.id, text_blocks=[TextBlock(text="ok")])


@pytest.mark.parametrize(
    ("filename", "content_type", "expected_backend"),
    [
        ("a.txt", DocumentType.TEXT, "text"),
        ("a.md", DocumentType.MARKDOWN, "markdown"),
        ("a.html", DocumentType.HTML, "html"),
        ("a.docx", DocumentType.DOCX, "docx"),
        ("a.doc", DocumentType.DOC, "doc"),
        ("a.pptx", DocumentType.PPTX, "pptx"),
        ("a.eml", DocumentType.EML, "eml"),
        ("a.png", DocumentType.IMAGE, "image"),
        ("a.svg", DocumentType.IMAGE, "image"),
        ("a.gif", DocumentType.IMAGE, "image"),
        ("a.webp", DocumentType.IMAGE, "image"),
        ("a.bmp", DocumentType.IMAGE, "image"),
        ("a.pdf", DocumentType.PDF, "marker"),
        ("a.mp3", DocumentType.AUDIO, "local_whisper"),
        ("a.mp4", DocumentType.VIDEO, "local_whisper"),
    ],
)
def test_resolve_backend(filename: str, content_type: DocumentType, expected_backend: str) -> None:
    disp = ParserDispatcher(_config())
    assert disp._resolve_backend(content_type, Document.type_extension(filename)) == expected_backend


def test_resolve_pdf_backend_variants() -> None:
    assert ParserDispatcher(_config(pdf="DoclingLoader"))._resolve_pdf_backend() == "docling"
    assert ParserDispatcher(_config(pdf="PyMuPDFLoader"))._resolve_pdf_backend() == "pymupdf"
    assert ParserDispatcher(_config(pdf="DotsOCRLoader"))._resolve_pdf_backend() == "pdf_client"


def test_resolve_audio_backend_openai() -> None:
    disp = ParserDispatcher(_config(audio="OpenAIAudioLoader"))
    assert disp._resolve_audio_backend("mp3") == "audio_client"


def test_audio_client_receives_live_transcription_prompt_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.workers.parsers.parser_dispatcher as dispatcher

    async def resolver() -> str | None:
        return "Keep speaker labels."

    monkeypatch.setattr(dispatcher, "_create", lambda _module, _name, **kwargs: kwargs["client"])

    client = ParserDispatcher(
        _config(audio="OpenAIAudioLoader"),
        transcription_prompt_resolver=resolver,
    )._build_audio_client()

    assert client._transcription_prompt_resolver is resolver


def test_audio_client_receives_live_stt_endpoint_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.workers.parsers.parser_dispatcher as dispatcher
    from core.config.model_endpoints import ModelEndpointConfig

    endpoint = ModelEndpointConfig(endpoint="http://moss:8000/v1", model_name="moss-transcribe-diarize")

    def resolver() -> ModelEndpointConfig:
        return endpoint

    monkeypatch.setattr(dispatcher, "_create", lambda _module, _name, **kwargs: kwargs["client"])

    client = ParserDispatcher(
        _config(audio="OpenAIAudioLoader"),
        transcription_endpoint_resolver=resolver,
    )._build_audio_client()

    assert client._transcription_endpoint_resolver is resolver


def test_unsupported_pdf_config_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF loader"):
        ParserDispatcher(_config(pdf="NopeLoader"))._resolve_pdf_backend()


@pytest.mark.asyncio
async def test_parse_dispatches_to_cached_backend() -> None:
    disp = ParserDispatcher(_config())
    fake = _FakeParser()
    disp._by_name["marker"] = fake  # pre-seed so no real backend is built

    document = Document(filename="report.pdf", content_type=DocumentType.PDF, raw_bytes=b"%PDF-1.4")
    result = await disp.parse(document)

    assert fake.seen is document
    assert result.text_blocks[0].text == "ok"


@pytest.mark.asyncio
async def test_for_pdf_strategy_overrides_pdf_backend_and_shares_cache() -> None:
    """A preset's ``parsing_strategy`` must override the global PDF backend for
    PDFs while non-PDF types still dispatch normally — reusing the dispatcher's
    cached backends (no duplicate pools)."""
    disp = ParserDispatcher(_config(pdf="MarkerLoader"))  # global default = marker
    marker, pymupdf, text = _FakeParser(), _FakeParser(), _FakeParser()
    disp._by_name.update({"marker": marker, "pymupdf": pymupdf, "text": text})

    pdf_parser = disp.for_pdf_strategy("pymupdf")

    pdf = Document(filename="a.pdf", content_type=DocumentType.PDF, raw_bytes=b"%PDF-1.4")
    await pdf_parser.parse(pdf)
    assert pymupdf.seen is pdf  # routed to the preset strategy, not the global marker
    assert marker.seen is None

    txt = Document(filename="a.txt", content_type=DocumentType.TEXT, raw_bytes=b"hi")
    await pdf_parser.parse(txt)
    assert text.seen is txt  # non-PDF content still dispatches by content type


def test_for_pdf_strategy_rejects_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF parsing strategy"):
        ParserDispatcher(_config()).for_pdf_strategy("nope")


def test_pymupdf_backend_builds_in_markdown_mode_without_images() -> None:
    """The lightweight pymupdf backend builds in markdown mode — structured text
    for the markdown-aware chunker — but with embed_images=False so it never
    inlines base64 images into chunk text (which bloats chunks / breaks Milvus
    inserts). Images are marker/docling's job."""
    parser = ParserDispatcher(_config(pdf="PyMuPDFLoader"))._get("pymupdf")
    assert getattr(parser, "_mode", None) == "markdown"

    # The "without images" contract: build a PDF that actually contains an image
    # and confirm the markdown extractor produces NO ImageBlocks and inlines no
    # base64 data URIs. Catches a regression that re-enables embed_images.
    import io

    import pymupdf
    from core.indexing.parsers.pdf.pymupdf import _extract_markdown
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world.")
    page.insert_image(pymupdf.Rect(0, 0, 8, 8), stream=buf.getvalue())
    raw = doc.tobytes()
    doc.close()

    pages, images = _extract_markdown(raw, "doc.pdf")
    assert images == []  # pymupdf must not extract/inline images
    assert not any("data:image" in p for p in pages)


def test_build_caption_vlm_requires_endpoint() -> None:
    # No VLM endpoint configured -> unavailable, regardless of the captioning flag.
    assert build_caption_vlm(_config(image_captioning=True, vlm_base_url="")) is None
    assert build_caption_vlm(_config(image_captioning=False, vlm_base_url="")) is None


def test_build_caption_vlm_available_when_endpoint_set_even_if_globally_off() -> None:
    # Availability is decoupled from the captioning policy: an endpoint is enough
    # to build the VLM. Standalone-image captioning relies on this (the policy
    # gate lives in the pipeline, not here).
    assert build_caption_vlm(_config(image_captioning=False, vlm_base_url="http://vlm:8000/v1")) is not None


def test_build_caption_vlm_preserves_enable_thinking() -> None:
    vlm = build_caption_vlm(
        _config(
            image_captioning=False,
            vlm_base_url="http://vlm:8000/v1",
            vlm_enable_thinking=False,
        )
    )

    assert vlm._enable_thinking is False


def test_build_pdf_client_preserves_openai_loader_enable_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePdfClient:
        def __init__(self, vlm, concurrency_limit):
            self.vlm = vlm
            self.concurrency_limit = concurrency_limit

    import services.inference.parsers.dotsocr as dotsocr
    import services.workers.parsers.parser_dispatcher as dispatcher

    monkeypatch.setattr(dotsocr, "DotsOCRPdfClient", FakePdfClient)
    monkeypatch.setattr(dispatcher, "_create", lambda _module, _name, **kwargs: kwargs["client"])

    parser = ParserDispatcher(_config(pdf="DotsOCRLoader", openai_loader_enable_thinking=False))._build_pdf_client()

    assert parser.vlm._enable_thinking is False


def test_build_eml_wires_nested_email_parser_with_depth_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    disp = ParserDispatcher(_config())
    fallback_parser = _FakeParser()
    monkeypatch.setattr(disp, "_get", lambda name: fallback_parser)

    parser = disp._build_eml()

    assert parser._attachment_parsers["txt"] is fallback_parser
    assert "eml" in parser._attachment_parsers
    nested_1 = parser._attachment_parsers["eml"]
    nested_2 = nested_1._attachment_parsers["eml"]
    nested_3 = nested_2._attachment_parsers["eml"]
    assert "eml" not in nested_3._attachment_parsers


# ---------------------------------------------------------------------------
# The progress watchdog stamp (openrag_ingest_last_parse_completion_timestamp_seconds)
# ---------------------------------------------------------------------------


class _StubParser:
    """Minimal backend: returns a document, or raises."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def parse(self, document: Document) -> ProcessedDocument:
        if self.error is not None:
            raise self.error
        return ProcessedDocument(document_id=document.id, text_blocks=[TextBlock(text="x")])

    def supported_types(self) -> list[str]:
        return [doc_type.value for doc_type in DocumentType]


def _text_document() -> Document:
    return Document(filename="note.txt", raw_bytes=b"x", content_type=DocumentType.TEXT)


@pytest.mark.asyncio
async def test_successful_parse_stamps_the_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_parse_with`` is the single point where a parse has both a backend and a
    completion. Drop the stamp and ``openrag_ingest_last_parse_completion_timestamp_seconds``
    is never written; the gauge is then absent, and ``OpenRagIngestStalled`` — which
    reads ``time() - max(<gauge>)`` — silently cannot fire. An alert that cannot fire
    is indistinguishable from a healthy system, so the call site is pinned here and
    not only the recorder it calls.
    """
    import services.workers.parsers.parser_dispatcher as module

    stamped: list[str] = []
    monkeypatch.setattr(module, "record_parse_completion", lambda pool: stamped.append(pool))

    disp = ParserDispatcher(_config())
    monkeypatch.setattr(disp, "_get", lambda _name: _StubParser())

    await disp.parse(_text_document())

    assert stamped == ["text"]


@pytest.mark.asyncio
async def test_failed_parse_stamps_only_the_first_use_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed parse must not stamp a completion — a pool whose workers are
    wedged must stop updating it, which is what lets the watchdog's
    ``time() - <stamp>`` climb. The one stamp it leaves is the first-use seed.
    Also guards the success test above against passing for the wrong reason: a
    completion stamp placed before the parse would satisfy it too.
    """
    import core.observability.ray_metrics as rm
    import services.workers.parsers.parser_dispatcher as module

    stamped: list[str] = []
    seeded: list[str] = []
    monkeypatch.setattr(module, "record_parse_completion", lambda pool: stamped.append(pool))
    monkeypatch.setattr(rm, "_WATCHDOG_SEEDED", set())
    monkeypatch.setattr(rm, "record_parse_completion", lambda pool, **_: seeded.append(pool) or True)

    disp = ParserDispatcher(_config())
    monkeypatch.setattr(disp, "_get", lambda _name: _StubParser(error=RuntimeError("backend wedged")))

    with pytest.raises(RuntimeError, match="backend wedged"):
        await disp.parse(_text_document())

    assert stamped == []
    assert seeded == ["text"]


@pytest.mark.asyncio
async def test_a_preset_pdf_strategy_stamps_the_pool_that_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_PdfStrategyParser`` picks the backend itself, bypassing ``parse``. A
    PDF indexed under a preset's ``parsing_strategy`` must still stamp its
    pool, or the watchdog goes blind for the GPU parsers it exists for."""
    import services.workers.parsers.parser_dispatcher as module

    stamped: list[str] = []
    monkeypatch.setattr(module, "record_parse_completion", lambda pool: stamped.append(pool))

    disp = ParserDispatcher(_config(pdf="MarkerLoader"))
    disp._by_name.update({"marker": _FakeParser(), "pymupdf": _FakeParser()})
    pdf = Document(filename="a.pdf", content_type=DocumentType.PDF, raw_bytes=b"%PDF-1.4")

    await disp.for_pdf_strategy("pymupdf").parse(pdf)
    await disp.parse(pdf)

    assert stamped == ["pymupdf", "marker"]


@pytest.mark.asyncio
async def test_a_pool_that_never_completes_still_seeds_the_watchdog_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stamped on success only, a pool that fails from its first parse never
    produced the series, and ``time() - max(<stamp>)`` had nothing to age: the
    stall that starts at boot was invisible. Its first use is seeded, once per
    backend per process."""
    import core.observability.ray_metrics as rm

    stamped: list[str] = []
    monkeypatch.setattr(rm, "_WATCHDOG_SEEDED", set())
    monkeypatch.setattr(rm, "record_parse_completion", lambda pool, **_: stamped.append(pool) or True)

    disp = ParserDispatcher(_config())
    monkeypatch.setattr(disp, "_get", lambda _name: _StubParser(error=RuntimeError("backend wedged")))

    for _ in range(3):
        with pytest.raises(RuntimeError, match="backend wedged"):
            await disp.parse(_text_document())

    assert stamped == ["text"]


def test_building_the_dispatcher_leaves_pymupdf_on_its_thread():
    """The API replicas build this dispatcher for the direct-extract path. Only
    the indexer worker gives PyMuPDF its process pool (``configure_pymupdf_pool``),
    so building a dispatcher — and the PyMuPDF parser in it — must not."""
    from core.indexing.parsers.pdf import pymupdf as pymupdf_mod
    from services.workers.parsers.parser_dispatcher import build_parser_dispatcher

    # A config that asks for a pool, so pushing it from here would show.
    config = _config()
    config.loader.pymupdf_pool_size = 2
    config.loader.pymupdf_parse_memory_limit_mb = 512
    config.loader.pymupdf_max_tasks_per_child = 7
    pymupdf_mod.configure_pool(pymupdf_mod.PyMuPDFPoolSettings())
    disp = build_parser_dispatcher(config)
    disp._get("pymupdf")

    assert pymupdf_mod._POOL_SETTINGS == pymupdf_mod.PyMuPDFPoolSettings()
    assert pymupdf_mod._get_pool().uses_processes is False


def test_configure_pymupdf_pool_pushes_the_loader_settings():
    from core.indexing.parsers.pdf import pymupdf as pymupdf_mod
    from services.workers.parsers.parser_dispatcher import configure_pymupdf_pool

    loader = SimpleNamespace(pymupdf_pool_size=3, pymupdf_parse_memory_limit_mb=512, pymupdf_max_tasks_per_child=7)
    try:
        configure_pymupdf_pool(SimpleNamespace(loader=loader))
        assert pymupdf_mod._POOL_SETTINGS == pymupdf_mod.PyMuPDFPoolSettings(
            max_workers=3, memory_limit_mb=512, max_tasks_per_child=7
        )
    finally:
        pymupdf_mod.configure_pool(pymupdf_mod.PyMuPDFPoolSettings())


# --------------------------------------------------------------------------- #
# OCR fallback for PDFs without a text layer (mycollections#152)
# --------------------------------------------------------------------------- #


class _PagesParser:
    """Returns one block per entry of ``pages`` (page numbers from 1)."""

    def __init__(self, pages: list[str], parse_info: dict | None = None) -> None:
        self.pages = pages
        self.parse_info = parse_info or {}
        self.calls = 0

    def supported_types(self) -> list[str]:
        return []

    async def parse(self, document: Document) -> ProcessedDocument:
        self.calls += 1
        return ProcessedDocument(
            document_id=document.id,
            text_blocks=[TextBlock(text=text, page_number=i) for i, text in enumerate(self.pages, start=1)],
            page_count=len(self.pages),
            parse_info=dict(self.parse_info),
        )


def _ocr_config(fallback: str = "marker", *, min_chars: int = 20, ratio: float = 0.5) -> SimpleNamespace:
    config = _config(pdf="PyMuPDFLoader")
    config.loader.ocr_fallback = fallback
    config.loader.ocr_fallback_min_chars_per_page = min_chars
    config.loader.ocr_fallback_empty_page_ratio = ratio
    return config


def _pdf() -> Document:
    return Document(id="d1", filename="scan.pdf", content_type=DocumentType.PDF)


SCANNED = ["", "  ", "-----", ""]
TYPED = ["A first page with plenty of real words on it.", "And a second one, just as readable as the first."]


@pytest.mark.asyncio
async def test_a_pdf_without_text_layer_is_reparsed_with_the_ocr_backend() -> None:
    disp = ParserDispatcher(_ocr_config("marker"))
    pymupdf, marker = _PagesParser(SCANNED), _PagesParser(["Texte reconnu par OCR sur la page un."] * 4)
    disp._by_name.update({"pymupdf": pymupdf, "marker": marker})

    processed = await disp.parse(_pdf())

    assert (pymupdf.calls, marker.calls) == (1, 1)
    assert processed.text_blocks[0].text.startswith("Texte reconnu")
    assert processed.parse_info == {"backend": "marker", "ocr": True, "ocr_fallback": True}


@pytest.mark.asyncio
async def test_a_born_digital_pdf_is_never_rerouted() -> None:
    disp = ParserDispatcher(_ocr_config("marker"))
    pymupdf, marker = _PagesParser(TYPED), _PagesParser(["unused"])
    disp._by_name.update({"pymupdf": pymupdf, "marker": marker})

    processed = await disp.parse(_pdf())

    assert marker.calls == 0
    assert processed.parse_info == {"backend": "pymupdf", "ocr": False}


@pytest.mark.asyncio
async def test_ocr_fallback_none_keeps_the_empty_parse() -> None:
    disp = ParserDispatcher(_ocr_config("none"))
    pymupdf, marker = _PagesParser(SCANNED), _PagesParser(["unused"])
    disp._by_name.update({"pymupdf": pymupdf, "marker": marker})

    processed = await disp.parse(_pdf())

    assert marker.calls == 0
    assert processed.parse_info == {"backend": "pymupdf", "ocr": False}


@pytest.mark.asyncio
async def test_a_mostly_typed_pdf_stays_under_the_empty_page_ratio() -> None:
    """One blank page out of three is a separator, not a scan."""
    disp = ParserDispatcher(_ocr_config("docling", ratio=0.5))
    pymupdf, docling = _PagesParser([TYPED[0], "", TYPED[1]]), _PagesParser(["unused"])
    disp._by_name.update({"pymupdf": pymupdf, "docling": docling})

    await disp.parse(_pdf())

    assert docling.calls == 0


@pytest.mark.asyncio
async def test_an_ocr_backend_is_not_reparsed() -> None:
    disp = ParserDispatcher(_ocr_config("docling"))
    marker, docling = _PagesParser(SCANNED), _PagesParser(["unused"])
    disp._by_name.update({"marker": marker, "docling": docling})

    processed = await disp.for_pdf_strategy("marker").parse(_pdf())

    assert docling.calls == 0
    assert processed.parse_info == {"backend": "marker", "ocr": True}


@pytest.mark.asyncio
async def test_a_preset_pymupdf_strategy_also_falls_back() -> None:
    disp = ParserDispatcher(_ocr_config("marker"))
    disp._config.loader.file_loaders.pdf = "MarkerLoader"
    pymupdf, marker = _PagesParser(SCANNED), _PagesParser(["Texte reconnu par OCR sur la page un."])
    disp._by_name.update({"pymupdf": pymupdf, "marker": marker})

    processed = await disp.for_pdf_strategy("pymupdf").parse(_pdf())

    assert processed.parse_info["ocr_fallback"] is True


@pytest.mark.asyncio
async def test_a_failing_ocr_backend_fails_the_document() -> None:
    class _Broken(_PagesParser):
        async def parse(self, document: Document) -> ProcessedDocument:
            raise RuntimeError("marker pool unavailable")

    disp = ParserDispatcher(_ocr_config("marker"))
    disp._by_name.update({"pymupdf": _PagesParser(SCANNED), "marker": _Broken([])})

    with pytest.raises(RuntimeError, match="marker pool unavailable"):
        await disp.parse(_pdf())


@pytest.mark.asyncio
async def test_non_pdf_documents_are_stamped_with_their_backend() -> None:
    disp = ParserDispatcher(_ocr_config("marker"))
    disp._by_name["text"] = _FakeParser()

    processed = await disp.parse(Document(id="t", filename="a.txt", content_type=DocumentType.TEXT))

    assert processed.parse_info == {"backend": "text", "ocr": False}


def test_unknown_ocr_fallback_is_rejected() -> None:
    disp = ParserDispatcher(_ocr_config("tesseract"))
    with pytest.raises(ValueError, match="Unsupported OCR fallback"):
        disp._ocr_fallback_backend()


def test_pdf_client_is_a_preset_strategy() -> None:
    from core.config.indexation_pipeline import PARSING_STRATEGIES, IndexationPipelineConfig

    assert "pdf_client" in PARSING_STRATEGIES
    assert IndexationPipelineConfig(parsing_strategy="pdf_client").parsing_strategy == "pdf_client"
    disp = ParserDispatcher(_config())
    disp._by_name["pdf_client"] = _FakeParser()
    assert disp.for_pdf_strategy("pdf_client") is not None


def test_spreadsheet_backend_gets_the_loader_bounds():
    config = _config()
    config.loader.spreadsheet_max_cells = 1234
    config.loader.spreadsheet_columns_per_group = 7
    config.loader.spreadsheet_include_hidden_sheets = True
    disp = ParserDispatcher(config)

    assert disp._resolve_backend(DocumentType.SPREADSHEET, "xlsx") == "spreadsheet"
    parser = disp._get("spreadsheet")
    assert (parser._max_cells, parser._columns_per_group, parser._include_hidden) == (1234, 7, True)
