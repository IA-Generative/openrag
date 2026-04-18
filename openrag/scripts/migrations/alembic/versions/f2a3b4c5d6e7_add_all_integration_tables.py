"""Add all integration tables: indexing profiles, Q&A, feedback, announcements, drive sources

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Indexing profiles
    op.create_table(
        "indexing_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("chunker_name", sa.String(50), nullable=False, server_default="recursive_splitter"),
        sa.Column("chunk_size", sa.Integer, nullable=False, server_default="512"),
        sa.Column("chunk_overlap_rate", sa.String, nullable=False, server_default="0.2"),
        sa.Column("contextual_retrieval", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("contextualization_timeout", sa.Integer, nullable=False, server_default="120"),
        sa.Column("max_concurrent_contextualization", sa.Integer, nullable=False, server_default="10"),
        sa.Column("retriever_type", sa.String(50), nullable=False, server_default="single"),
        sa.Column("retriever_top_k", sa.Integer, nullable=False, server_default="50"),
        sa.Column("similarity_threshold", sa.String, nullable=False, server_default="0.6"),
        sa.Column("extra_params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "partition_indexing_config",
        sa.Column("partition_name", sa.String, sa.ForeignKey("partitions.partition", ondelete="CASCADE"), primary_key=True),
        sa.Column("indexing_profile_id", sa.Integer, sa.ForeignKey("indexing_profiles.id"), nullable=False),
        sa.Column("overrides", sa.JSON, nullable=False, server_default="{}"),
    )

    # Q&A entries
    op.create_table(
        "qa_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("partition_name", sa.String, sa.ForeignKey("partitions.partition", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("question", sa.String, nullable=False),
        sa.Column("expected_answer", sa.String, nullable=True),
        sa.Column("override_answer", sa.String, nullable=True),
        sa.Column("override_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("tags", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("source_feedback_id", sa.Integer, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Q&A eval runs
    op.create_table(
        "qa_eval_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("partition_name", sa.String, sa.ForeignKey("partitions.partition", ondelete="CASCADE"), nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("results", sa.JSON, nullable=True),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # User feedback
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("external_user_id", sa.String, nullable=True, index=True),
        sa.Column("partition_name", sa.String, nullable=True, index=True),
        sa.Column("question", sa.String, nullable=False),
        sa.Column("response", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("reason", sa.String, nullable=True),
        sa.Column("owui_chat_id", sa.String, nullable=True),
        sa.Column("owui_message_id", sa.String, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("promoted_to_qa_id", sa.Integer, sa.ForeignKey("qa_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("owui_chat_id", "owui_message_id", name="uix_owui_feedback"),
        sa.CheckConstraint("rating BETWEEN -1 AND 1", name="ck_feedback_rating"),
    )

    # Notification channels
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('webhook','email_smtp','tchap_bot')", name="ck_channel_type"),
    )

    # Announcements
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String, nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_value", sa.String, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime, nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("channels", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('announcement','poll')", name="ck_announcement_type"),
        sa.CheckConstraint("target_type IN ('all','partition','group','user')", name="ck_target_type"),
        sa.CheckConstraint("status IN ('draft','scheduled','sent','closed')", name="ck_announcement_status"),
    )

    # Poll options
    op.create_table(
        "poll_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("announcement_id", sa.Integer, sa.ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )

    # Poll responses
    op.create_table(
        "poll_responses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("announcement_id", sa.Integer, sa.ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("poll_option_id", sa.Integer, sa.ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_user_id", sa.String, nullable=False),
        sa.Column("responded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("announcement_id", "external_user_id", name="uix_poll_one_vote"),
    )

    # Drive sources
    op.create_table(
        "drive_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("partition_name", sa.String, sa.ForeignKey("partitions.partition", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("drive_base_url", sa.String, nullable=False),
        sa.Column("drive_folder_id", sa.String, nullable=False),
        sa.Column("sync_frequency_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("sync_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("last_sync_status", sa.String(20), nullable=True),
        sa.Column("last_sync_error", sa.String, nullable=True),
        sa.Column("auth_mode", sa.String(20), nullable=False, server_default="service_account"),
        sa.Column("service_account_client_id", sa.String, nullable=True),
        sa.Column("service_account_client_secret", sa.String, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("partition_name", "drive_folder_id", name="uix_partition_drive_folder"),
    )

    # Drive file mappings
    op.create_table(
        "drive_file_mappings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drive_source_id", sa.Integer, sa.ForeignKey("drive_sources.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("drive_item_id", sa.String, nullable=False),
        sa.Column("drive_item_title", sa.String, nullable=True),
        sa.Column("drive_item_updated_at", sa.DateTime, nullable=True),
        sa.Column("file_id", sa.String, nullable=False),
        sa.Column("partition_name", sa.String, nullable=False),
        sa.Column("last_synced_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("drive_source_id", "drive_item_id", name="uix_drive_source_item"),
    )


def downgrade() -> None:
    op.drop_table("drive_file_mappings")
    op.drop_table("drive_sources")
    op.drop_table("poll_responses")
    op.drop_table("poll_options")
    op.drop_table("announcements")
    op.drop_table("notification_channels")
    op.drop_table("user_feedback")
    op.drop_table("qa_eval_runs")
    op.drop_table("qa_entries")
    op.drop_table("partition_indexing_config")
    op.drop_table("indexing_profiles")
