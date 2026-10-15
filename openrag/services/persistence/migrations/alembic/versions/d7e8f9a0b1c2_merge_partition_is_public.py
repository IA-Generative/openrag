"""merge the fork's partition is_public branch into the 2.3 head

Revision ID: d7e8f9a0b1c2
Revises: a7b8c9d0e1f2, c6d7e8f9a0b1
Create Date: 2026-10-15 00:00:00.000000

Fork-only. ``c6d7e8f9a0b1`` (``partitions.is_public``) was written on top of
2.2.1's head and is already applied on this fork's deployments, so it keeps
its parent: re-parenting it under 2.3's head would make Alembic believe the
2.3 revisions ran before it, and skip them on a database already at
``c6d7e8f9a0b1``. A merge lets both branches apply, in either order.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = ("a7b8c9d0e1f2", "c6d7e8f9a0b1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
