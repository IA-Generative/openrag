"""merge the fork's partition is_public branch into the 2.3.2 head

Revision ID: c6bd76e44f0c
Revises: 5e6d7c8b9a01, d7e8f9a0b1c2
Create Date: 2026-10-24 00:00:00.000000

Fork-only, same reasoning as ``d7e8f9a0b1c2``: the fork's head stays where
deployments already are, and 2.3.2's new revisions (up to ``5e6d7c8b9a01``)
join it through a merge instead of a re-parenting.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c6bd76e44f0c"
down_revision: str | Sequence[str] | None = ("5e6d7c8b9a01", "d7e8f9a0b1c2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
