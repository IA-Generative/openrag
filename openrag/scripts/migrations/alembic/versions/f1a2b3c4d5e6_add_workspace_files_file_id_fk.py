"""add FK from workspace_files.file_id (int) to files.id

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-03-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _file_id_is_integer() -> bool:
    """Check whether workspace_files.file_id is already an INTEGER (post-migration state)."""
    inspector = inspect(op.get_bind())
    for col in inspector.get_columns("workspace_files"):
        if col["name"] == "file_id":
            return isinstance(col["type"], sa.Integer)
    return False


def upgrade() -> None:
    """Migrate workspace_files.file_id from string to integer FK referencing files.id.

    Idempotent: Base.metadata.create_all() at app startup may have already
    created workspace_files with file_id as INTEGER on older deployments — in
    which case the conversion is a no-op.
    """
    if _file_id_is_integer():
        return

    # 1. Purge rows that have no matching file (no valid files.file_id to JOIN against).
    op.execute("DELETE FROM workspace_files WHERE file_id NOT IN (SELECT file_id FROM files)")

    # 2. Add a temporary integer column to hold the resolved files.id value.
    op.add_column("workspace_files", sa.Column("file_fk", sa.Integer(), nullable=True))

    # 3. Populate it by joining on the string file_id, scoped to the workspace's partition
    #    to resolve ambiguity when the same filename exists in multiple partitions.
    op.execute(
        "UPDATE workspace_files wf "
        "SET file_fk = f.id "
        "FROM files f "
        "JOIN workspaces w ON w.workspace_id = wf.workspace_id "
        "WHERE f.file_id = wf.file_id AND f.partition_name = w.partition_name"
    )

    # 3b. Drop any rows that couldn't be resolved (file_fk still NULL).
    op.execute("DELETE FROM workspace_files WHERE file_fk IS NULL")

    # 4. Drop the old string column and its index.
    op.drop_index("ix_workspace_files_file_id", table_name="workspace_files")
    op.drop_column("workspace_files", "file_id")

    # 5. Rename file_fk → file_id, make it NOT NULL.
    op.alter_column("workspace_files", "file_fk", new_column_name="file_id", nullable=False)

    # 6. Recreate the index, unique constraint, and FK.
    op.create_index("ix_workspace_files_file_id", "workspace_files", ["file_id"])
    op.create_unique_constraint("uix_workspace_file", "workspace_files", ["workspace_id", "file_id"])
    op.create_foreign_key(
        "fk_workspace_files_file_id",
        "workspace_files",
        "files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Revert workspace_files.file_id back to a string column."""
    op.drop_constraint("fk_workspace_files_file_id", "workspace_files", type_="foreignkey")
    op.drop_index("ix_workspace_files_file_id", table_name="workspace_files")

    # Re-add a string column and repopulate from files.file_id via JOIN.
    op.add_column("workspace_files", sa.Column("file_str", sa.String(), nullable=True))
    op.execute("UPDATE workspace_files wf SET file_str = f.file_id FROM files f WHERE f.id = wf.file_id")
    op.drop_column("workspace_files", "file_id")
    op.alter_column("workspace_files", "file_str", new_column_name="file_id", nullable=False)
    op.create_index("ix_workspace_files_file_id", "workspace_files", ["file_id"])
    op.create_unique_constraint("uix_workspace_file", "workspace_files", ["workspace_id", "file_id"])
