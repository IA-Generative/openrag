"""add file_count and file_quota

Revision ID: c224d4befe71
Revises: cd642e4502d8
Create Date: 2026-02-09 15:38:28.565172

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c224d4befe71"
down_revision: str | Sequence[str] | None = "cd642e4502d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("file_quota", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("files", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_files_created_by", "files", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_files_created_by", "files", ["created_by"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_files_created_by", table_name="files")
    op.drop_constraint("fk_files_created_by", "files", type_="foreignkey")
    op.drop_column("files", "created_by")
    op.drop_column("users", "file_count")
    op.drop_column("users", "file_quota")
