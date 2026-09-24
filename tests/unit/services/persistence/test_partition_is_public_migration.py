"""The ``partitions.is_public`` migration is idempotent in both directions."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[4] / "openrag" / "services" / "persistence" / "migrations" / "alembic"


@pytest.fixture
def migration(monkeypatch):
    monkeypatch.syspath_prepend(str(_VERSIONS))
    return importlib.import_module(
        "services.persistence.migrations.alembic.versions.c6d7e8f9a0b1_add_partition_is_public",
    )


class _FakeOp:
    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.dropped: list[tuple[str, str]] = []

    def add_column(self, table, column) -> None:
        self.added.append((table, column))

    def drop_column(self, table, column) -> None:
        self.dropped.append((table, column))


def test_revision_chain(migration) -> None:
    assert migration.revision == "c6d7e8f9a0b1"
    assert migration.down_revision == "b9c0d1e2f3a4"


def test_upgrade_adds_non_null_false_default_column(monkeypatch, migration) -> None:
    op = _FakeOp()
    monkeypatch.setattr(migration, "op", op)
    monkeypatch.setattr(migration, "column_exists", lambda _t, _c: False)

    migration.upgrade()

    [(table, column)] = op.added
    assert table == "partitions"
    assert column.name == "is_public"
    assert column.nullable is False
    assert str(column.server_default.arg) == "false"


def test_upgrade_skips_existing_column(monkeypatch, migration) -> None:
    op = _FakeOp()
    monkeypatch.setattr(migration, "op", op)
    monkeypatch.setattr(migration, "column_exists", lambda _t, _c: True)

    migration.upgrade()

    assert op.added == []


@pytest.mark.parametrize(("exists", "expected"), [(True, [("partitions", "is_public")]), (False, [])])
def test_downgrade_is_guarded(monkeypatch, migration, exists, expected) -> None:
    op = _FakeOp()
    monkeypatch.setattr(migration, "op", op)
    monkeypatch.setattr(migration, "column_exists", lambda _t, _c: exists)

    migration.downgrade()

    assert op.dropped == expected


def test_no_other_migration_revises_the_same_parent() -> None:
    """Guard against a second head forking off ``b9c0d1e2f3a4``."""
    pattern = re.compile(r'^down_revision[^=]*=\s*"b9c0d1e2f3a4"', re.MULTILINE)
    children = sorted(p.name for p in (_VERSIONS / "versions").glob("*.py") if pattern.search(p.read_text()))
    assert children == ["c6d7e8f9a0b1_add_partition_is_public.py"]
