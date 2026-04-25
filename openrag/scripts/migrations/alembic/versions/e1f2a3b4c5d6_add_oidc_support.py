"""Add OIDC support: source field on partition_memberships

Revision ID: e1f2a3b4c5d6
Revises: cd9b84278028
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "cd9b84278028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'source' column to partition_memberships
    op.add_column(
        "partition_memberships",
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    op.drop_column("partition_memberships", "source")
