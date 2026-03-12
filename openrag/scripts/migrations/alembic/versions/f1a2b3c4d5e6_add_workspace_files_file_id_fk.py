"""add FK from workspace_files.file_id to files.file_id

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-03-12 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add referential integrity constraint: workspace_files.file_id → files.file_id."""
    # Remove any ghost rows that have no matching file before adding the constraint.
    op.execute("DELETE FROM workspace_files WHERE file_id NOT IN (SELECT file_id FROM files)")
    op.create_foreign_key(
        "fk_workspace_files_file_id",
        "workspace_files",
        "files",
        ["file_id"],
        ["file_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove referential integrity constraint."""
    op.drop_constraint("fk_workspace_files_file_id", "workspace_files", type_="foreignkey")
