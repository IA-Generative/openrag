"""Unit tests for add_files_to_workspace validation.

Tests that get_existing_file_ids correctly identifies which file IDs are valid
for a given partition, enabling the router to reject ghost IDs before insertion.

Uses an in-memory SQLite database (no Ray, no real Postgres required).
"""

import pytest
from sqlalchemy import Column, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

TestBase = declarative_base()


class FileModel(TestBase):
    """Minimal File table for testing — no FK dependencies."""

    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, nullable=False)
    partition_name = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("file_id", "partition_name", name="uix_file_id_partition"),)


class WorkspaceModel(TestBase):
    """Minimal Workspace table for testing."""

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String, nullable=False, unique=True)
    partition_name = Column(String, nullable=False)


class WorkspaceFileModel(TestBase):
    """Minimal WorkspaceFile table for testing."""

    __tablename__ = "workspace_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String, nullable=False)
    file_id = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint("workspace_id", "file_id", name="uix_workspace_file"),)


class PartitionFileManagerHelper:
    """Minimal subset of PartitionFileManager for isolated testing."""

    def __init__(self, session_factory):
        self.Session = session_factory

    def add_file(self, partition: str, file_id: str):
        with self.Session() as session:
            session.add(FileModel(file_id=file_id, partition_name=partition))
            session.commit()

    def get_existing_file_ids(self, partition: str, file_ids: list[str]) -> set[str]:
        """Return the subset of file_ids that exist in the given partition."""
        from sqlalchemy import select

        with self.Session() as session:
            result = session.execute(
                select(FileModel.file_id).where(
                    FileModel.partition_name == partition,
                    FileModel.file_id.in_(file_ids),
                )
            )
            return {r[0] for r in result.all()}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    manager = PartitionFileManagerHelper(Session)
    yield manager
    engine.dispose()


# ---------------------------------------------------------------------------
# Tests for get_existing_file_ids
# ---------------------------------------------------------------------------


def test_all_file_ids_exist(db):
    db.add_file("p1", "file-a")
    db.add_file("p1", "file-b")

    result = db.get_existing_file_ids("p1", ["file-a", "file-b"])

    assert result == {"file-a", "file-b"}


def test_some_file_ids_missing(db):
    db.add_file("p1", "file-a")

    result = db.get_existing_file_ids("p1", ["file-a", "ghost-id"])

    assert result == {"file-a"}


def test_no_file_ids_exist(db):
    result = db.get_existing_file_ids("p1", ["ghost-1", "ghost-2"])

    assert result == set()


def test_empty_input_returns_empty(db):
    db.add_file("p1", "file-a")

    result = db.get_existing_file_ids("p1", [])

    assert result == set()


def test_file_in_different_partition_not_returned(db):
    db.add_file("p1", "file-a")
    # file-a exists in p1 but we query p2
    result = db.get_existing_file_ids("p2", ["file-a"])

    assert result == set()


def test_cross_partition_isolation(db):
    db.add_file("p1", "file-a")
    db.add_file("p2", "file-b")

    result = db.get_existing_file_ids("p1", ["file-a", "file-b"])

    # file-b is in p2, not p1 — should not be returned
    assert result == {"file-a"}


def test_duplicate_ids_in_input(db):
    db.add_file("p1", "file-a")

    result = db.get_existing_file_ids("p1", ["file-a", "file-a"])

    assert result == {"file-a"}
