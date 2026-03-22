"""Root Settings model and cached singleton."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from .mixins import ConfigMixin
from .models import (
    ChunkerConfig,
    EmbedderConfig,
    LLMConfig,
    LLMContextConfig,
    LLMParamsConfig,
    LoaderConfig,
    MapReduceConfig,
    PathsConfig,
    PromptsConfig,
    RAGConfig,
    RayConfig,
    RDBConfig,
    RerankerConfig,
    RetrieverConfig,
    SemaphoreConfig,
    ServerConfig,
    VectorDBConfig,
    VerboseConfig,
    VLMConfig,
    WebSearchConfig,
)


class Settings(ConfigMixin):
    """Root configuration — composes all sub-models.

    Defaults here are fallbacks only. In production, values come from
    conf/config.yaml merged with environment variable overrides.
    """

    llm_params: LLMParamsConfig = Field(default_factory=LLMParamsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    semaphore: SemaphoreConfig = Field(default_factory=SemaphoreConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    vectordb: VectorDBConfig = Field(default_factory=VectorDBConfig)
    rdb: RDBConfig = Field(default_factory=RDBConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    map_reduce: MapReduceConfig = Field(default_factory=MapReduceConfig)
    verbose: VerboseConfig = Field(default_factory=VerboseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    llm_context: LLMContextConfig = Field(default_factory=LLMContextConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    loader: LoaderConfig = Field(default_factory=LoaderConfig)
    ray: RayConfig = Field(default_factory=RayConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    retriever: RetrieverConfig = Field(default_factory=RetrieverConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    websearch: WebSearchConfig = Field(default_factory=WebSearchConfig)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — one Settings instance per process."""
    from .loader import load_config

    return load_config()
