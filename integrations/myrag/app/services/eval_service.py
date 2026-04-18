"""RAG Evaluation Service — test and score system prompts."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path


@dataclass
class EvalQuestion:
    id: str
    question: str
    expected_answer: str
    must_cite: list[str] = field(default_factory=list)
    must_not_cite: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalResult:
    question_id: str
    question: str
    expected: str
    actual: str
    similarity_score: float
    citation_score: float
    overall_score: float
    cited_articles: list[str] = field(default_factory=list)
    missing_citations: list[str] = field(default_factory=list)
    unwanted_citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalRun:
    id: str
    collection: str
    prompt_used: str
    status: str = "pending"  # pending, running, done, failed
    total_questions: int = 0
    completed_questions: int = 0
    avg_score: float = 0.0
    results: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class EvalService:
    """Manages evaluation datasets and scoring runs."""

    def __init__(self, data_dir: str | None = None):
        from app.config import settings
        self.data_dir = data_dir or settings.data_dir

    def _questions_path(self, collection: str) -> Path:
        return Path(self.data_dir) / collection / "eval_questions.json"

    def _runs_path(self, collection: str) -> Path:
        return Path(self.data_dir) / collection / "eval_runs.json"

    # --- Dataset management ---

    def add_question(self, collection: str, question: str, expected_answer: str,
                     must_cite: list[str] | None = None,
                     must_not_cite: list[str] | None = None,
                     tags: list[str] | None = None) -> EvalQuestion:
        questions = self.list_questions(collection)
        q = EvalQuestion(
            id=str(uuid.uuid4())[:8],
            question=question,
            expected_answer=expected_answer,
            must_cite=must_cite or [],
            must_not_cite=must_not_cite or [],
            tags=tags or [],
        )
        questions.append(q)
        self._save_questions(collection, questions)
        return q

    def list_questions(self, collection: str) -> list[EvalQuestion]:
        path = self._questions_path(collection)
        if not path.exists():
            return []
        return [EvalQuestion(**q) for q in json.loads(path.read_text())]

    def delete_question(self, collection: str, question_id: str):
        questions = [q for q in self.list_questions(collection) if q.id != question_id]
        self._save_questions(collection, questions)

    def import_dataset(self, collection: str, data: list[dict]):
        questions = self.list_questions(collection)
        for item in data:
            questions.append(EvalQuestion(
                id=str(uuid.uuid4())[:8],
                question=item["question"],
                expected_answer=item.get("expected_answer", ""),
                must_cite=item.get("must_cite", []),
                must_not_cite=item.get("must_not_cite", []),
                tags=item.get("tags", []),
            ))
        self._save_questions(collection, questions)

    def export_dataset(self, collection: str) -> list[dict]:
        return [q.to_dict() for q in self.list_questions(collection)]

    def _save_questions(self, collection: str, questions: list[EvalQuestion]):
        path = self._questions_path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([q.to_dict() for q in questions], indent=2, ensure_ascii=False))

    # --- Scoring ---

    @staticmethod
    def _score_similarity(expected: str, actual: str) -> float:
        """Score text similarity (0-1)."""
        if not expected or not actual:
            return 0.0
        return SequenceMatcher(None, expected.lower(), actual.lower()).ratio()

    @staticmethod
    def _score_citations(response: str, must_cite: list[str], must_not_cite: list[str]) -> float:
        """Score citation correctness (0-1)."""
        if not must_cite and not must_not_cite:
            return 1.0

        # Extract article IDs from response
        found = set(re.findall(r"\b([LRD]\d+(?:-\d+)*)\b", response))

        # Check must_cite
        cite_score = 0.0
        if must_cite:
            cited = sum(1 for c in must_cite if c in found)
            cite_score = cited / len(must_cite)
        else:
            cite_score = 1.0

        # Check must_not_cite (penalty)
        penalty = 0.0
        if must_not_cite:
            unwanted = sum(1 for c in must_not_cite if c in found or c.lower() in response.lower())
            penalty = unwanted * 0.2  # -0.2 per unwanted citation

        return max(0.0, min(1.0, cite_score - penalty))

    def score_response(self, question: EvalQuestion, actual_response: str) -> EvalResult:
        """Score a single response against the expected answer."""
        sim = self._score_similarity(question.expected_answer, actual_response)
        cit = self._score_citations(actual_response, question.must_cite, question.must_not_cite)

        # Weighted: 50% similarity + 50% citations
        overall = sim * 0.5 + cit * 0.5

        found = set(re.findall(r"\b([LRD]\d+(?:-\d+)*)\b", actual_response))
        missing = [c for c in question.must_cite if c not in found]
        unwanted = [c for c in question.must_not_cite if c in found or c.lower() in actual_response.lower()]

        return EvalResult(
            question_id=question.id,
            question=question.question,
            expected=question.expected_answer,
            actual=actual_response,
            similarity_score=round(sim, 3),
            citation_score=round(cit, 3),
            overall_score=round(overall, 3),
            cited_articles=sorted(found),
            missing_citations=missing,
            unwanted_citations=unwanted,
        )

    # --- Runs ---

    def create_run(self, collection: str, prompt_used: str) -> EvalRun:
        questions = self.list_questions(collection)
        run = EvalRun(
            id=str(uuid.uuid4())[:8],
            collection=collection,
            prompt_used=prompt_used,
            total_questions=len(questions),
        )
        runs = self._load_runs(collection)
        runs.append(run)
        self._save_runs(collection, runs)
        return run

    def list_runs(self, collection: str) -> list[EvalRun]:
        return self._load_runs(collection)

    def get_run(self, collection: str, run_id: str) -> EvalRun | None:
        for run in self._load_runs(collection):
            if run.id == run_id:
                return run
        return None

    def update_run(self, collection: str, run: EvalRun):
        runs = self._load_runs(collection)
        runs = [r if r.id != run.id else run for r in runs]
        self._save_runs(collection, runs)

    def _load_runs(self, collection: str) -> list[EvalRun]:
        path = self._runs_path(collection)
        if not path.exists():
            return []
        return [EvalRun(**r) for r in json.loads(path.read_text())]

    def _save_runs(self, collection: str, runs: list[EvalRun]):
        path = self._runs_path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([r.to_dict() for r in runs], indent=2, ensure_ascii=False))
