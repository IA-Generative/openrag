from .base import BaseReranker
from .infinity import InfinityReranker
from .openai_reranker import OpenAIReranker

RERANKER_MAPPING = {
    "infinity": InfinityReranker,
    "openai": OpenAIReranker,
}


class RerankerFactory:
    @staticmethod
    def get_reranker(config: dict) -> BaseReranker:
        provider = config.reranker.get("provider")
        reranker_class = RERANKER_MAPPING.get(provider, None)

        if not reranker_class:
            raise ValueError(f"Unsupported reranker provider: {provider}")

        return reranker_class(config)
