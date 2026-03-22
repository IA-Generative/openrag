"""Pydantic config models for each configuration section.

Each model corresponds to a section in the old .hydra_config/config.yaml.
All defaults mirror the original YAML values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from .mixins import ConfigMixin, _env, _env_bool, _env_float, _env_int


# ---------------------------------------------------------------------------
# LLM params (shared anchor in the old YAML)
# ---------------------------------------------------------------------------
class LLMParamsConfig(ConfigMixin):
    temperature: float = 0.1
    timeout: int = 60
    max_retries: int = 2
    logprobs: bool = True


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
class LLMConfig(LLMParamsConfig):
    base_url: str = ""
    model: str = ""
    api_key: str = ""

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            base_url=_env("BASE_URL", ""),
            model=_env("MODEL", ""),
            api_key=_env("API_KEY", ""),
        )


# ---------------------------------------------------------------------------
# VLM
# ---------------------------------------------------------------------------
class VLMConfig(LLMParamsConfig):
    base_url: str = ""
    model: str = ""
    api_key: str = ""

    @classmethod
    def from_env(cls) -> VLMConfig:
        return cls(
            base_url=_env("VLM_BASE_URL", ""),
            model=_env("VLM_MODEL", ""),
            api_key=_env("VLM_API_KEY", ""),
        )


# ---------------------------------------------------------------------------
# Semaphore
# ---------------------------------------------------------------------------
class SemaphoreConfig(ConfigMixin):
    llm_semaphore: int = 10
    vlm_semaphore: int = 10

    @classmethod
    def from_env(cls) -> SemaphoreConfig:
        return cls(
            llm_semaphore=_env_int("LLM_SEMAPHORE", 10),
            vlm_semaphore=_env_int("VLM_SEMAPHORE", 10),
        )


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------
class EmbedderConfig(ConfigMixin):
    provider: str = "openai"
    model_name: str = "jinaai/jina-embeddings-v3"
    base_url: str = "http://vllm:8000/v1"
    api_key: str = "EMPTY"
    max_model_len: int = 8192

    @classmethod
    def from_env(cls) -> EmbedderConfig:
        return cls(
            model_name=_env("EMBEDDER_MODEL_NAME", "jinaai/jina-embeddings-v3"),
            base_url=_env("EMBEDDER_BASE_URL", "http://vllm:8000/v1"),
            api_key=_env("EMBEDDER_API_KEY", "EMPTY"),
            max_model_len=_env_int("MAX_MODEL_LEN", 8192),
        )


# ---------------------------------------------------------------------------
# VectorDB
# ---------------------------------------------------------------------------
class VectorDBConfig(ConfigMixin):
    host: str = "milvus"
    port: int = 19530
    connector_name: str = "milvus"
    collection_name: str = "vdb_test"
    hybrid_search: bool = True
    enable: bool = True

    @classmethod
    def from_env(cls) -> VectorDBConfig:
        return cls(
            host=_env("VDB_HOST", "milvus"),
            port=_env_int("VDB_iPORT", 19530),
            connector_name=_env("VDB_CONNECTOR_NAME", "milvus"),
            collection_name=_env("VDB_COLLECTION_NAME", "vdb_test"),
            hybrid_search=_env_bool("VDB_HYBRID_SEARCH", True),
        )


# ---------------------------------------------------------------------------
# RDB (Postgres)
# ---------------------------------------------------------------------------
class RDBConfig(ConfigMixin):
    host: str = "rdb"
    port: int = 5432
    user: str = "root"
    password: str = "root_password"
    default_file_quota: int = -1

    @classmethod
    def from_env(cls) -> RDBConfig:
        return cls(
            host=_env("POSTGRES_HOST", "rdb"),
            port=_env_int("POSTGRES_PORT", 5432),
            user=_env("POSTGRES_USER", "root"),
            password=_env("POSTGRES_PASSWORD", "root_password"),
            default_file_quota=_env_int("DEFAULT_FILE_QUOTA", -1),
        )


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------
class RerankerConfig(ConfigMixin):
    enable: bool = True
    model_name: str = "Alibaba-NLP/gte-multilingual-reranker-base"
    top_k: int = 10
    base_url: str = ""

    @classmethod
    def from_env(cls) -> RerankerConfig:
        base_url = _env("RERANKER_BASE_URL")
        if not base_url:
            port = _env("RERANKER_PORT", "7997")
            base_url = f"http://reranker:{port}"

        return cls(
            enable=_env_bool("RERANKER_ENABLED", True),
            model_name=_env("RERANKER_MODEL", "Alibaba-NLP/gte-multilingual-reranker-base"),
            top_k=_env_int("RERANKER_TOP_K", 10),
            base_url=base_url,
        )


# ---------------------------------------------------------------------------
# MapReduce
# ---------------------------------------------------------------------------
class MapReduceConfig(ConfigMixin):
    initial_batch_size: int = 10
    expansion_batch_size: int = 5
    max_total_documents: int = 20
    debug: bool = False

    @classmethod
    def from_env(cls) -> MapReduceConfig:
        return cls(
            initial_batch_size=_env_int("MAP_REDUCE_INITIAL_BATCH_SIZE", 10),
            expansion_batch_size=_env_int("MAP_REDUCE_EXPANSION_BATCH_SIZE", 5),
            max_total_documents=_env_int("MAP_REDUCE_MAX_TOTAL_DOCUMENTS", 20),
            debug=_env_bool("MAP_REDUCE_DEBUG", False),
        )


# ---------------------------------------------------------------------------
# Verbose
# ---------------------------------------------------------------------------
class VerboseConfig(ConfigMixin):
    level: str = "DEBUG"

    @classmethod
    def from_env(cls) -> VerboseConfig:
        return cls(level=_env("LOG_LEVEL", "DEBUG"))


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class ServerConfig(ConfigMixin):
    preferred_url_scheme: str | None = None

    @classmethod
    def from_env(cls) -> ServerConfig:
        val = _env("PREFERRED_URL_SCHEME")
        if val and val.lower() == "null":
            val = None
        return cls(preferred_url_scheme=val)


# ---------------------------------------------------------------------------
# LLM Context
# ---------------------------------------------------------------------------
class LLMContextConfig(ConfigMixin):
    max_llm_context_size: int = 8192
    max_output_tokens: int = 1024

    @classmethod
    def from_env(cls) -> LLMContextConfig:
        return cls(
            max_llm_context_size=_env_int("MAX_LLM_CONTEXT_SIZE", 8192),
            max_output_tokens=_env_int("MAX_OUTPUT_TOKENS", 1024),
        )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
class PathsConfig(ConfigMixin):
    prompts_dir: Path = Path("../prompts/example1")
    data_dir: Path = Path("../data")
    db_dir: Path = Path("/app/db")
    log_dir: Path = Path("/app/logs")

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_env(cls) -> PathsConfig:
        return cls(
            prompts_dir=Path(_env("PROMPTS_DIR", "../prompts/example1")).resolve(),
            data_dir=Path(_env("DATA_DIR", "../data")).resolve(),
            db_dir=Path(_env("DB_DIR", "/app/db")),
            log_dir=Path(_env("LOG_DIR", "/app/logs")).resolve(),
        )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
class PromptsConfig(ConfigMixin):
    sys_prompt: str = "sys_prompt_tmpl.txt"
    query_contextualizer: str = "query_contextualizer_tmpl.txt"
    chunk_contextualizer: str = "chunk_contextualizer_tmpl.txt"
    image_describer: str = "image_captioning_tmpl.txt"
    spoken_style_answer: str = "spoken_style_answer_tmpl.txt"
    hyde: str = "hyde.txt"
    multi_query: str = "multi_query_pmpt_tmpl.txt"


# ---------------------------------------------------------------------------
# Transcriber (nested under loader)
# ---------------------------------------------------------------------------
class TranscriberConfig(ConfigMixin):
    base_url: str = "http://transcriber:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "openai/whisper-large-v3-turbo"
    timeout: int = 3600
    max_concurrent_chunks: int = 20
    use_whisper_lang_detector: bool = True

    @classmethod
    def from_env(cls) -> TranscriberConfig:
        return cls(
            base_url=_env("TRANSCRIBER_BASE_URL", "http://transcriber:8000/v1"),
            api_key=_env("TRANSCRIBER_API_KEY", "EMPTY"),
            model_name=_env("TRANSCRIBER_MODEL", "openai/whisper-large-v3-turbo"),
            timeout=_env_int("TRANSCRIBER_TIMEOUT", 3600),
            max_concurrent_chunks=_env_int("TRANSCRIBER_MAX_CONCURRENT_CHUNKS", 20),
            use_whisper_lang_detector=_env_bool("USE_WHISPER_LANG_DETECTOR", True),
        )


# ---------------------------------------------------------------------------
# OpenAI Loader (nested under loader)
# ---------------------------------------------------------------------------
class OpenAILoaderConfig(ConfigMixin):
    base_url: str = "http://openai:8000/v1"
    api_key: str = "EMPTY"
    model: str = "dotsocr-model"
    temperature: float = 0.2
    timeout: int = 180
    max_retries: int = 2
    top_p: float = 0.9
    concurrency_limit: int = 20

    @classmethod
    def from_env(cls) -> OpenAILoaderConfig:
        return cls(
            base_url=_env("OPENAI_LOADER_BASE_URL", "http://openai:8000/v1"),
            api_key=_env("OPENAI_LOADER_API_KEY", "EMPTY"),
            model=_env("OPENAI_LOADER_MODEL", "dotsocr-model"),
            temperature=_env_float("OPENAI_LOADER_TEMPERATURE", 0.2),
            timeout=_env_int("OPENAI_LOADER_TIMEOUT", 180),
            max_retries=_env_int("OPENAI_LOADER_MAX_RETRIES", 2),
            top_p=_env_float("OPENAI_LOADER_TOP_P", 0.9),
            concurrency_limit=_env_int("OPENAI_LOADER_CONCURRENCY_LIMIT", 20),
        )


# ---------------------------------------------------------------------------
# Local Whisper (nested under loader)
# ---------------------------------------------------------------------------
class LocalWhisperConfig(ConfigMixin):
    model: str = "base"
    whisper_n_workers: int = 3
    whisper_num_gpus: float = 0.01
    whisper_concurency_per_worker: int = 2

    @classmethod
    def from_env(cls) -> LocalWhisperConfig:
        return cls(
            model=_env("WHISPER_MODEL", "base"),
            whisper_n_workers=_env_int("WHISPER_N_WORKERS", 3),
            whisper_num_gpus=_env_float("WHISPER_NUM_GPUS", 0.01),
            whisper_concurency_per_worker=_env_int("WHISPER_CONCURRENCY_PER_WORKER", 2),
        )


# ---------------------------------------------------------------------------
# File loaders mapping (nested under loader)
# ---------------------------------------------------------------------------
class FileLoadersConfig(ConfigMixin):
    txt: str = "TextLoader"
    pdf: str = "MarkerLoader"
    eml: str = "EmlLoader"
    docx: str = "DocxLoader"
    pptx: str = "PPTXLoader"
    doc: str = "DocLoader"
    png: str = "ImageLoader"
    jpeg: str = "ImageLoader"
    jpg: str = "ImageLoader"
    svg: str = "ImageLoader"
    wav: str = "LocalWhisperLoader"
    mp3: str = "LocalWhisperLoader"
    flac: str = "LocalWhisperLoader"
    ogg: str = "LocalWhisperLoader"
    aac: str = "LocalWhisperLoader"
    flv: str = "LocalWhisperLoader"
    wma: str = "LocalWhisperLoader"
    mp4: str = "LocalWhisperLoader"
    md: str = "MarkdownLoader"

    @classmethod
    def from_env(cls) -> FileLoadersConfig:
        audio_loader = _env("AUDIOLOADER", "LocalWhisperLoader")
        return cls(
            pdf=_env("PDFLoader", "MarkerLoader"),
            wav=audio_loader,
            mp3=audio_loader,
            flac=audio_loader,
            ogg=audio_loader,
            aac=audio_loader,
            flv=audio_loader,
            wma=audio_loader,
            mp4=audio_loader,
        )


# ---------------------------------------------------------------------------
# Mimetypes mapping (nested under loader)
# ---------------------------------------------------------------------------
class MimetypesConfig(ConfigMixin):
    """Maps MIME type strings to file extensions.

    Stored as regular fields so Pydantic serialization works normally.
    Access via dict() or .items() for iteration.
    """

    model_config = {"extra": "allow"}

    text_plain: str = Field(default=".txt", alias="text/plain")
    text_markdown: str = Field(default=".md", alias="text/markdown")
    application_pdf: str = Field(default=".pdf", alias="application/pdf")
    message_rfc822: str = Field(default=".eml", alias="message/rfc822")
    application_docx: str = Field(
        default=".docx",
        alias="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    application_pptx: str = Field(
        default=".pptx",
        alias="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    application_msword: str = Field(default=".doc", alias="application/msword")
    image_png: str = Field(default=".png", alias="image/png")
    image_jpeg: str = Field(default=".jpeg", alias="image/jpeg")
    audio_wav: str = Field(default=".wav", alias="audio/wav")
    audio_mpeg: str = Field(default=".mp3", alias="audio/mpeg")
    audio_flac: str = Field(default=".flac", alias="audio/flac")
    audio_ogg: str = Field(default=".ogg", alias="audio/ogg")
    audio_aac: str = Field(default=".aac", alias="audio/aac")
    video_x_flv: str = Field(default=".flv", alias="video/x-flv")
    audio_x_ms_wma: str = Field(default=".wma", alias="audio/x-ms-wma")
    video_mp4: str = Field(default=".mp4", alias="video/mp4")

    model_config = {"extra": "allow", "populate_by_name": True}

    def to_dict(self) -> dict[str, str]:
        """Return {mime_type: extension} mapping using aliases as keys."""
        result = {}
        for field_name, field_info in self.model_fields.items():
            alias = field_info.alias or field_name
            result[alias] = getattr(self, field_name)
        return result


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
class LoaderConfig(ConfigMixin):
    image_captioning: bool = True
    image_captioning_url: bool = True
    save_markdown: bool = False
    mimetypes: MimetypesConfig = Field(default_factory=MimetypesConfig)
    local_whisper: LocalWhisperConfig = Field(default_factory=LocalWhisperConfig)
    file_loaders: FileLoadersConfig = Field(default_factory=FileLoadersConfig)
    marker_max_tasks_per_child: int = 10
    marker_pool_size: int = 1
    marker_max_processes: int = 2
    marker_min_processes: int = 1
    marker_num_gpus: float = 0.01
    marker_timeout: int = 3600
    marker_pdftext_workers: int = 2
    transcriber: TranscriberConfig = Field(default_factory=TranscriberConfig)
    openai: OpenAILoaderConfig = Field(default_factory=OpenAILoaderConfig)

    @classmethod
    def from_env(cls) -> LoaderConfig:
        return cls(
            image_captioning=_env_bool("IMAGE_CAPTIONING", True),
            image_captioning_url=_env_bool("IMAGE_CAPTIONING_URL", True),
            save_markdown=_env_bool("SAVE_MARKDOWN", False),
            local_whisper=LocalWhisperConfig.from_env(),
            file_loaders=FileLoadersConfig.from_env(),
            marker_max_tasks_per_child=_env_int("MARKER_MAX_TASKS_PER_CHILD", 10),
            marker_pool_size=_env_int("MARKER_POOL_SIZE", 1),
            marker_max_processes=_env_int("MARKER_MAX_PROCESSES", 2),
            marker_min_processes=_env_int("MARKER_MIN_PROCESSES", 1),
            marker_num_gpus=_env_float("MARKER_NUM_GPUS", 0.01),
            marker_timeout=_env_int("MARKER_TIMEOUT", 3600),
            marker_pdftext_workers=_env_int("MARKER_PDFTEXT_WORKERS", 2),
            transcriber=TranscriberConfig.from_env(),
            openai=OpenAILoaderConfig.from_env(),
        )


# ---------------------------------------------------------------------------
# Ray — Indexer concurrency groups
# ---------------------------------------------------------------------------
class IndexerConcurrencyGroupsConfig(ConfigMixin):
    default: int = 1000
    update: int = 100
    search: int = 100
    delete: int = 100
    serialize: int = 50
    chunk: int = 1000
    insert: int = 100

    @classmethod
    def from_env(cls) -> IndexerConcurrencyGroupsConfig:
        return cls(
            default=_env_int("INDEXER_DEFAULT_CONCURRENCY", 1000),
            update=_env_int("INDEXER_UPDATE_CONCURRENCY", 100),
            search=_env_int("INDEXER_SEARCH_CONCURRENCY", 100),
            delete=_env_int("INDEXER_DELETE_CONCURRENCY", 100),
            serialize=_env_int("INDEXER_SERIALIZE_CONCURRENCY", 50),
            chunk=_env_int("INDEXER_CHUNK_CONCURRENCY", 1000),
            insert=_env_int("INDEXER_INSERT_CONCURRENCY", 100),
        )


class RayIndexerConfig(ConfigMixin):
    max_task_retries: int = 2
    serialize_timeout: int = 3600
    vectordb_timeout: int = 30
    concurrency_groups: IndexerConcurrencyGroupsConfig = Field(
        default_factory=IndexerConcurrencyGroupsConfig,
    )

    @classmethod
    def from_env(cls) -> RayIndexerConfig:
        return cls(
            max_task_retries=_env_int("RAY_MAX_TASK_RETRIES", 2),
            serialize_timeout=_env_int("INDEXER_SERIALIZE_TIMEOUT", 3600),
            vectordb_timeout=_env_int("VECTORDB_TIMEOUT", 30),
            concurrency_groups=IndexerConcurrencyGroupsConfig.from_env(),
        )


class RaySemaphoreConfig(ConfigMixin):
    concurrency: int = 100000

    @classmethod
    def from_env(cls) -> RaySemaphoreConfig:
        return cls(concurrency=_env_int("RAY_SEMAPHORE_CONCURRENCY", 100000))


class RayServeConfig(ConfigMixin):
    enable: bool = False
    num_replicas: int = 1
    host: str = "0.0.0.0"
    port: int = 8080
    chainlit_port: int = 8090

    @classmethod
    def from_env(cls) -> RayServeConfig:
        return cls(
            enable=_env_bool("ENABLE_RAY_SERVE", False),
            num_replicas=_env_int("RAY_SERVE_NUM_REPLICAS", 1),
            host=_env("RAY_SERVE_HOST", "0.0.0.0"),
            port=_env_int("RAY_SERVE_PORT", 8080),
            chainlit_port=_env_int("CHAINLIT_PORT", 8090),
        )


class RayConfig(ConfigMixin):
    num_gpus: float = 0.01
    pool_size: int = 1
    max_tasks_per_worker: int = 8
    indexer: RayIndexerConfig = Field(default_factory=RayIndexerConfig)
    semaphore: RaySemaphoreConfig = Field(default_factory=RaySemaphoreConfig)
    serve: RayServeConfig = Field(default_factory=RayServeConfig)

    @classmethod
    def from_env(cls) -> RayConfig:
        return cls(
            num_gpus=_env_float("RAY_NUM_GPUS", 0.01),
            pool_size=_env_int("RAY_POOL_SIZE", 1),
            max_tasks_per_worker=_env_int("RAY_MAX_TASKS_PER_WORKER", 8),
            indexer=RayIndexerConfig.from_env(),
            semaphore=RaySemaphoreConfig.from_env(),
            serve=RayServeConfig.from_env(),
        )


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------
class ChunkerConfig(ConfigMixin):
    name: str = "recursive_splitter"
    contextual_retrieval: bool = True
    contextualization_timeout: int = 120
    max_concurrent_contextualization: int = 10
    chunk_size: int = 512
    chunk_overlap_rate: float = 0.2

    @classmethod
    def from_env(cls) -> ChunkerConfig:
        return cls(
            name=_env("CHUNKER", "recursive_splitter"),
            contextual_retrieval=_env_bool("CONTEXTUAL_RETRIEVAL", True),
            contextualization_timeout=_env_int("CONTEXTUALIZATION_TIMEOUT", 120),
            max_concurrent_contextualization=_env_int("MAX_CONCURRENT_CONTEXTUALIZATION", 10),
            chunk_size=_env_int("CHUNK_SIZE", 512),
            chunk_overlap_rate=_env_float("CHUNK_OVERLAP_RATE", 0.2),
        )


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------
class RetrieverConfig(ConfigMixin):
    type: str = "single"
    top_k: int = 50
    similarity_threshold: float = 0.6
    with_surrounding_chunks: bool = False
    include_related: bool = True
    include_ancestors: bool = True
    related_limit: int = 10
    max_ancestor_depth: int = 10
    k_queries: int = 3
    combine: bool = False

    @classmethod
    def from_env(cls) -> RetrieverConfig:
        return cls(
            type=_env("RETRIEVER_TYPE", "single"),
            top_k=_env_int("RETRIEVER_TOP_K", 50),
            similarity_threshold=_env_float("SIMILARITY_THRESHOLD", 0.6),
            with_surrounding_chunks=_env_bool("WITH_SURROUNDING_CHUNKS", False),
            include_related=_env_bool("INCLUDE_RELATED", True),
            include_ancestors=_env_bool("INCLUDE_ANCESTORS", True),
            related_limit=_env_int("RELATED_LIMIT", 10),
            max_ancestor_depth=_env_int("MAX_DEPTH", 10),
        )


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
class RAGConfig(ConfigMixin):
    mode: str = "ChatBotRag"
    chat_history_depth: int = 4
    max_contextualized_query_len: int = 512

    @classmethod
    def from_env(cls) -> RAGConfig:
        return cls(
            mode=_env("RAG_MODE", "ChatBotRag"),
        )


# ---------------------------------------------------------------------------
# WebSearch
# ---------------------------------------------------------------------------
class WebSearchConfig(ConfigMixin):
    provider: str = "staan"
    api_token: str = ""
    base_url: str = "https://api.staan.ai/search/web"
    top_k: int = 5
    lang: str = "fr-FR"
    max_tokens: int = 2000
    fetch_content: bool = True
    fetch_max_results: int = 3
    fetch_timeout: float = 1.0
    fetch_max_tokens: int = 500
    fetch_verify_ssl: bool = False

    @classmethod
    def from_env(cls) -> WebSearchConfig:
        return cls(
            provider=_env("WEBSEARCH_PROVIDER", "staan"),
            api_token=_env("WEBSEARCH_API_TOKEN", ""),
            base_url=_env("WEBSEARCH_BASE_URL", "https://api.staan.ai/search/web"),
            top_k=_env_int("WEBSEARCH_TOP_K", 5),
            lang=_env("WEBSEARCH_LANG", "fr-FR"),
            max_tokens=_env_int("WEBSEARCH_MAX_TOKENS", 2000),
            fetch_content=_env_bool("WEBSEARCH_FETCH_CONTENT", True),
            fetch_max_results=_env_int("WEBSEARCH_FETCH_MAX_RESULTS", 3),
            fetch_timeout=_env_float("WEBSEARCH_FETCH_TIMEOUT", 1.0),
            fetch_max_tokens=_env_int("WEBSEARCH_FETCH_MAX_TOKENS", 500),
            fetch_verify_ssl=_env_bool("WEBSEARCH_FETCH_VERIFY_SSL", False),
        )
