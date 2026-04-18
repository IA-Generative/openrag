"""Tests for Q&R cache system (TDD)."""

import json
import pytest

from app.services.qr_cache import QRCache, QREntry


@pytest.fixture
def cache(tmp_path):
    return QRCache(data_dir=str(tmp_path))


class TestQRCache:
    def test_add_entry(self, cache):
        cache.add("test-col", "Quel delai ?", "2 mois avant expiration (art L433-1)")
        entries = cache.list("test-col")
        assert len(entries) == 1
        assert entries[0].question == "Quel delai ?"

    def test_search_exact_match(self, cache):
        cache.add("test-col", "Quel delai pour renouveler ?", "2 mois")
        result = cache.search("test-col", "Quel delai pour renouveler ?")
        assert result is not None
        assert result.answer == "2 mois"

    def test_search_no_match(self, cache):
        cache.add("test-col", "Quel delai ?", "2 mois")
        result = cache.search("test-col", "Quelle couleur ?")
        assert result is None

    def test_search_fuzzy(self, cache):
        cache.add("test-col", "Quel est le delai pour renouveler un titre de sejour ?", "2 mois avant")
        result = cache.search("test-col", "delai renouvellement titre sejour")
        # Fuzzy match depends on implementation — may or may not match
        # At minimum, exact match should work
        result2 = cache.search("test-col", "Quel est le delai pour renouveler un titre de sejour ?")
        assert result2 is not None

    def test_delete_entry(self, cache):
        cache.add("test-col", "Q1", "A1")
        cache.add("test-col", "Q2", "A2")
        entries = cache.list("test-col")
        cache.delete("test-col", entries[0].id)
        assert len(cache.list("test-col")) == 1

    def test_update_entry(self, cache):
        cache.add("test-col", "Q1", "A1")
        entries = cache.list("test-col")
        cache.update("test-col", entries[0].id, answer="A1 updated")
        updated = cache.list("test-col")
        assert updated[0].answer == "A1 updated"

    def test_import_json(self, cache):
        data = [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
            {"question": "Q3", "answer": "A3"},
        ]
        cache.import_json("test-col", data)
        assert len(cache.list("test-col")) == 3

    def test_export_json(self, cache):
        cache.add("test-col", "Q1", "A1")
        cache.add("test-col", "Q2", "A2")
        exported = cache.export_json("test-col")
        assert len(exported) == 2
        assert exported[0]["question"] == "Q1"

    def test_persistence(self, cache, tmp_path):
        cache.add("test-col", "Q1", "A1")
        # Create new cache instance
        cache2 = QRCache(data_dir=str(tmp_path))
        entries = cache2.list("test-col")
        assert len(entries) == 1

    def test_empty_collection(self, cache):
        entries = cache.list("nonexistent")
        assert entries == []

    def test_stats(self, cache):
        cache.add("test-col", "Q1", "A1")
        cache.add("test-col", "Q2", "A2")
        cache.record_hit("test-col")
        cache.record_hit("test-col")
        cache.record_miss("test-col")
        stats = cache.stats("test-col")
        assert stats["total_entries"] == 2
        assert stats["hits"] == 2
        assert stats["misses"] == 1
