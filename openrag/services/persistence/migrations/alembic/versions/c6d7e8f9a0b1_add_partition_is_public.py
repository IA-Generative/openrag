"""add partitions.is_public

Revision ID: c6d7e8f9a0b1
Revises: b9c0d1e2f3a4
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from schema_helpers import column_exists

# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: str | Sequence[str] | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``is_public`` flag to ``partitions`` (default: private).

    Idempotent: ``metadata.create_all()`` at app startup may already have
    created the column from the current model on a fresh database.
    """
    if not column_exists("partitions", "is_public"):
        op.add_column(
            "partitions",
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    if column_exists("partitions", "is_public"):
        op.drop_column("partitions", "is_public")
