"""Add workflow_runs table.

Revision ID: 003_workflow_runs
Revises: 002_seed_data
Create Date: 2026-04-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "003_workflow_runs"
down_revision = "002_seed_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chain_id", UUID(as_uuid=True), sa.ForeignKey("prompt_chains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("output_format", sa.String(10), nullable=False),
        sa.Column("filename_prefix", sa.String(200), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("source_ids", JSONB, nullable=False),
        sa.Column("total_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_file_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_step_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_file_name", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("results", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_workflow_runs_status")
    op.drop_index("idx_workflow_runs_user_id")
    op.drop_table("workflow_runs")
