"""Q&A override check for the RAG pipeline.

Before running the full RAG pipeline, checks if the user's question
matches an active Q&A override entry. If so, returns the override
answer directly, bypassing retrieval and generation.

Uses semantic similarity via the embedder to find matching questions.
"""

import os

from config import load_config
from openai import AsyncOpenAI
from utils.logger import get_logger

logger = get_logger()
config = load_config()

QA_OVERRIDE_THRESHOLD = float(os.getenv("QA_OVERRIDE_THRESHOLD", "0.92"))
QA_OVERRIDE_ENABLED = os.getenv("QA_OVERRIDE_ENABLED", "true").lower() == "true"


async def check_qa_override(question: str, partitions: list[str] | None = None) -> dict | None:
    """Check if a question matches an active Q&A override.

    Args:
        question: The user's question
        partitions: Optional list of partition names to filter overrides

    Returns:
        Dict with override info if match found, None otherwise.
        {"qa_id": int, "answer": str, "similarity": float}
    """
    if not QA_OVERRIDE_ENABLED:
        return None

    try:
        from components.indexer.vectordb.utils import QAEntry
        from utils.dependencies import get_vectordb

        vectordb = get_vectordb()
        pfm = await vectordb.get_partition_file_manager.remote()

        with pfm.Session() as s:
            query = s.query(QAEntry).filter(
                QAEntry.override_active.is_(True),
                QAEntry.override_answer.isnot(None),
            )
            if partitions:
                query = query.filter(QAEntry.partition_name.in_(partitions))
            overrides = query.all()

        if not overrides:
            return None

        # Use the embedder to compute similarity
        embedder_client = AsyncOpenAI(
            base_url=config.embedder["base_url"],
            api_key=config.embedder.get("api_key", "EMPTY"),
        )

        # Embed the question
        response = await embedder_client.embeddings.create(
            model=config.embedder["model_name"],
            input=[question] + [o.question for o in overrides],
        )

        question_embedding = response.data[0].embedding

        best_match = None
        best_similarity = 0.0

        for i, override in enumerate(overrides):
            override_embedding = response.data[i + 1].embedding
            # Cosine similarity
            dot_product = sum(a * b for a, b in zip(question_embedding, override_embedding))
            norm_q = sum(a * a for a in question_embedding) ** 0.5
            norm_o = sum(a * a for a in override_embedding) ** 0.5
            similarity = dot_product / (norm_q * norm_o) if (norm_q * norm_o) > 0 else 0

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = override

        if best_match and best_similarity >= QA_OVERRIDE_THRESHOLD:
            logger.info(
                "Q&A override matched",
                qa_id=best_match.id,
                similarity=round(best_similarity, 4),
                question=question[:100],
            )
            return {
                "qa_id": best_match.id,
                "answer": best_match.override_answer,
                "similarity": round(best_similarity, 4),
            }

        return None

    except Exception as e:
        logger.warning("Q&A override check failed, falling through to RAG", error=str(e))
        return None
