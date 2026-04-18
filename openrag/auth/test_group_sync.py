"""Tests for OIDC group sync on PartitionFileManager.

These tests use an in-memory SQLite database to test the actual
sync_oidc_memberships_additive and sync_oidc_memberships_authoritative methods.
"""

import pytest
from components.indexer.vectordb.utils import (
    Base,
    Partition,
    PartitionFileManager,
    PartitionMembership,
    User,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def pfm(tmp_path):
    """Create a PartitionFileManager with an in-memory SQLite DB."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    # Patch to avoid the postgres-specific database_exists check
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    pfm = object.__new__(PartitionFileManager)
    pfm.engine = engine
    pfm.Session = Session
    pfm.logger = __import__("utils.logger", fromlist=["get_logger"]).get_logger()
    pfm.file_quota_per_user = -1

    # Create a test user
    with Session() as s:
        user = User(id=10, display_name="Test User", is_admin=False)
        s.add(user)
        s.commit()

    return pfm


@pytest.fixture
def pfm_with_partitions(pfm):
    """PFM with pre-existing partitions."""
    with pfm.Session() as s:
        s.add(Partition(partition="finance"))
        s.add(Partition(partition="legal"))
        s.add(Partition(partition="hr"))
        s.commit()
    return pfm


class TestAdditiveSync:
    def test_creates_new_memberships(self, pfm_with_partitions):
        pfm = pfm_with_partitions
        pfm.sync_oidc_memberships_additive(10, {"finance": "viewer", "legal": "editor"})

        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10).all()
            by_partition = {m.partition_name: m for m in memberships}

        assert "finance" in by_partition
        assert by_partition["finance"].role == "viewer"
        assert by_partition["finance"].source == "oidc"
        assert "legal" in by_partition
        assert by_partition["legal"].role == "editor"

    def test_upgrades_role_never_downgrades(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        # First sync: viewer
        pfm.sync_oidc_memberships_additive(10, {"finance": "viewer"})
        # Second sync: upgrade to editor
        pfm.sync_oidc_memberships_additive(10, {"finance": "editor"})

        with pfm.Session() as s:
            m = s.query(PartitionMembership).filter_by(user_id=10, partition_name="finance").first()
            assert m.role == "editor"

        # Third sync: try to downgrade to viewer — should NOT downgrade
        pfm.sync_oidc_memberships_additive(10, {"finance": "viewer"})

        with pfm.Session() as s:
            m = s.query(PartitionMembership).filter_by(user_id=10, partition_name="finance").first()
            assert m.role == "editor"  # stays editor

    def test_does_not_remove_existing(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        pfm.sync_oidc_memberships_additive(10, {"finance": "viewer", "legal": "editor"})
        # Second sync only mentions finance
        pfm.sync_oidc_memberships_additive(10, {"finance": "viewer"})

        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10).all()
            partitions = {m.partition_name for m in memberships}

        # legal should still be there
        assert "legal" in partitions
        assert "finance" in partitions

    def test_creates_partition_if_not_exists(self, pfm):
        pfm.sync_oidc_memberships_additive(10, {"new-partition": "viewer"})

        with pfm.Session() as s:
            p = s.query(Partition).filter_by(partition="new-partition").first()
            assert p is not None
            m = s.query(PartitionMembership).filter_by(user_id=10, partition_name="new-partition").first()
            assert m is not None
            assert m.role == "viewer"


class TestAuthoritativeSync:
    def test_creates_and_removes_oidc_memberships(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        # First sync
        pfm.sync_oidc_memberships_authoritative(10, {"finance": "viewer", "legal": "editor"})
        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10).all()
            assert len(memberships) == 2

        # Second sync: remove legal, keep finance
        pfm.sync_oidc_memberships_authoritative(10, {"finance": "editor"})
        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10).all()
            by_partition = {m.partition_name: m for m in memberships}

        assert len(by_partition) == 1
        assert "finance" in by_partition
        assert by_partition["finance"].role == "editor"

    def test_does_not_touch_manual_memberships(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        # Add a manual membership
        with pfm.Session() as s:
            s.add(PartitionMembership(
                partition_name="hr", user_id=10, role="owner", source="manual"
            ))
            s.commit()

        # Authoritative sync with only finance
        pfm.sync_oidc_memberships_authoritative(10, {"finance": "viewer"})

        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10).all()
            by_partition = {m.partition_name: m for m in memberships}

        # hr (manual) should still exist
        assert "hr" in by_partition
        assert by_partition["hr"].source == "manual"
        assert by_partition["hr"].role == "owner"
        # finance (oidc) should exist
        assert "finance" in by_partition
        assert by_partition["finance"].source == "oidc"

    def test_converts_manual_to_oidc_when_desired(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        # Add a manual membership
        with pfm.Session() as s:
            s.add(PartitionMembership(
                partition_name="finance", user_id=10, role="viewer", source="manual"
            ))
            s.commit()

        # Authoritative sync claims finance as editor
        pfm.sync_oidc_memberships_authoritative(10, {"finance": "editor"})

        with pfm.Session() as s:
            m = s.query(PartitionMembership).filter_by(user_id=10, partition_name="finance").first()
            assert m.source == "oidc"
            assert m.role == "editor"

    def test_empty_desired_removes_all_oidc(self, pfm_with_partitions):
        pfm = pfm_with_partitions

        pfm.sync_oidc_memberships_authoritative(10, {"finance": "viewer", "legal": "editor"})
        pfm.sync_oidc_memberships_authoritative(10, {})

        with pfm.Session() as s:
            memberships = s.query(PartitionMembership).filter_by(user_id=10, source="oidc").all()
            assert len(memberships) == 0
