"""Tests for RAG evaluation system (TDD)."""

from __future__ import annotations

import pytest

from app.services.eval_service import EvalService, EvalQuestion, EvalRun


@pytest.fixture
def svc(tmp_path):
    return EvalService(data_dir=str(tmp_path))


class TestEvalDataset:
    def test_add_question(self, svc):
        svc.add_question("col", "Q1?", "A1", must_cite=["L423-1"])
        questions = svc.list_questions("col")
        assert len(questions) == 1
        assert questions[0].must_cite == ["L423-1"]

    def test_import_dataset(self, svc):
        data = [
            {"question": "Q1?", "expected_answer": "A1", "must_cite": ["L110-1"]},
            {"question": "Q2?", "expected_answer": "A2"},
        ]
        svc.import_dataset("col", data)
        assert len(svc.list_questions("col")) == 2

    def test_export_dataset(self, svc):
        svc.add_question("col", "Q1?", "A1")
        exported = svc.export_dataset("col")
        assert len(exported) == 1
        assert exported[0]["question"] == "Q1?"

    def test_delete_question(self, svc):
        svc.add_question("col", "Q1?", "A1")
        questions = svc.list_questions("col")
        svc.delete_question("col", questions[0].id)
        assert len(svc.list_questions("col")) == 0


class TestEvalScoring:
    def test_score_text_similarity(self, svc):
        score = svc._score_similarity("Le delai est de 2 mois", "Le delai est de 2 mois")
        assert score == 1.0

    def test_score_partial_similarity(self, svc):
        score = svc._score_similarity("Le delai est de 2 mois", "delai de 3 mois")
        assert 0.3 < score < 0.9

    def test_score_citations(self, svc):
        score = svc._score_citations(
            response="Selon l'article L423-1 et L110-1",
            must_cite=["L423-1", "L110-1"],
            must_not_cite=["AGDREF"],
        )
        assert score == 1.0

    def test_score_citations_missing(self, svc):
        score = svc._score_citations(
            response="Pas d'article cite",
            must_cite=["L423-1"],
            must_not_cite=[],
        )
        assert score == 0.0

    def test_score_citations_pollution(self, svc):
        score = svc._score_citations(
            response="Article L423-1 et AGDREF",
            must_cite=["L423-1"],
            must_not_cite=["AGDREF"],
        )
        assert score < 1.0  # penalized for AGDREF

    def test_create_run(self, svc):
        run = svc.create_run("col", "test-prompt")
        assert run.collection == "col"
        assert run.status == "pending"

    def test_list_runs(self, svc):
        svc.create_run("col", "prompt1")
        svc.create_run("col", "prompt2")
        runs = svc.list_runs("col")
        assert len(runs) == 2
