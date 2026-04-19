"""Add DocAgent tables.

Revision ID: 009_docagent
Revises: 008_docforge
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "009_docagent"
down_revision = "009_wiki_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "docagent_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("user_prompt", sa.Text, nullable=False),
        sa.Column("model_used", sa.String(200), nullable=False),
        sa.Column("source_filename", sa.String(500), nullable=True),
        sa.Column("source_storage_path", sa.Text, nullable=True),
        sa.Column("source_extracted_text", sa.Text, nullable=True),
        sa.Column("analysis_result", JSONB, nullable=True),
        sa.Column("plan_result", JSONB, nullable=True),
        sa.Column("content_result", JSONB, nullable=True),
        sa.Column("output_storage_path", sa.Text, nullable=True),
        sa.Column("output_filename", sa.String(500), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_docagent_jobs_user_id", "docagent_jobs", ["user_id"])
    op.create_index("idx_docagent_jobs_status", "docagent_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_docagent_jobs_status")
    op.drop_index("idx_docagent_jobs_user_id")
    op.drop_table("docagent_jobs")
