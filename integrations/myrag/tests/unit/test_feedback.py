"""Tests for feedback system (TDD)."""

from __future__ import annotations

import pytest

from app.services.feedback_service import FeedbackService, Feedback


@pytest.fixture
def svc(tmp_path):
    return FeedbackService(data_dir=str(tmp_path))


class TestFeedback:
    def test_ingest(self, svc):
        svc.ingest("col", "Q1?", "Response1", rating=1, user_id="eric")
        items = svc.list("col")
        assert len(items) == 1
        assert items[0].rating == 1

    def test_ingest_negative(self, svc):
        svc.ingest("col", "Q1?", "Bad response", rating=-1, reason="Incorrect")
        items = svc.list("col")
        assert items[0].rating == -1
        assert items[0].reason == "Incorrect"

    def test_idempotent(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=1, owui_message_id="msg-1")
        svc.ingest("col", "Q1?", "R1", rating=-1, owui_message_id="msg-1")
        items = svc.list("col")
        assert len(items) == 1  # deduplicated
        assert items[0].rating == -1  # updated

    def test_list_filter_status(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        svc.ingest("col", "Q2?", "R2", rating=1)
        pending = svc.list("col", status="pending")
        assert len(pending) == 2

    def test_review(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        items = svc.list("col")
        svc.review(items[0].id, "col", status="reviewed", reviewed_by="admin")
        updated = svc.get("col", items[0].id)
        assert updated.status == "reviewed"

    def test_promote_to_qr(self, svc):
        svc.ingest("col", "Q1?", "Bad answer", rating=-1)
        items = svc.list("col")
        svc.promote(items[0].id, "col", promote_to="qr")
        updated = svc.get("col", items[0].id)
        assert updated.status == "promoted"
        assert updated.promoted_to == "qr"

    def test_promote_to_eval(self, svc):
        svc.ingest("col", "Q1?", "Bad answer", rating=-1)
        items = svc.list("col")
        svc.promote(items[0].id, "col", promote_to="eval")
        updated = svc.get("col", items[0].id)
        assert updated.promoted_to == "eval"

    def test_ignore(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=-1)
        items = svc.list("col")
        svc.review(items[0].id, "col", status="ignored")
        updated = svc.get("col", items[0].id)
        assert updated.status == "ignored"

    def test_stats(self, svc):
        svc.ingest("col", "Q1?", "R1", rating=1)
        svc.ingest("col", "Q2?", "R2", rating=1)
        svc.ingest("col", "Q3?", "R3", rating=-1)
        stats = svc.stats("col")
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1
        assert stats["satisfaction_rate"] == pytest.approx(0.667, abs=0.01)
        assert stats["pending_review"] == 3

    def test_persistence(self, svc, tmp_path):
        svc.ingest("col", "Q1?", "R1", rating=1)
        svc2 = FeedbackService(data_dir=str(tmp_path))
        assert len(svc2.list("col")) == 1
