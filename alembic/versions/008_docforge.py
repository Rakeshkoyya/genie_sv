"""Add DocForge tables for document templates.

Revision ID: 008_docforge
Revises: 003_workflow_runs
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "008_docforge"
down_revision = "003_workflow_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DocForge templates
    op.create_table(
        "docforge_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("original_storage_path", sa.Text, nullable=False),
        sa.Column("template_storage_path", sa.Text, nullable=False),
        sa.Column("html_preview", sa.Text, nullable=True),
        sa.Column("placeholders", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_docforge_templates_user_id", "docforge_templates", ["user_id"])

    # DocForge folders
    op.create_table(
        "docforge_folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_docforge_folders_user_name"),
    )
    op.create_index("idx_docforge_folders_user_id", "docforge_folders", ["user_id"])

    # DocForge generated documents
    op.create_table(
        "docforge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("docforge_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("docforge_folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("placeholder_values", JSONB, nullable=False, server_default="{}"),
        sa.Column("storage_path", sa.Text, nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_docforge_documents_user_id", "docforge_documents", ["user_id"])
    op.create_index("idx_docforge_documents_template_id", "docforge_documents", ["template_id"])
    op.create_index("idx_docforge_documents_folder_id", "docforge_documents", ["folder_id"])


def downgrade() -> None:
    op.drop_index("idx_docforge_documents_folder_id")
    op.drop_index("idx_docforge_documents_template_id")
    op.drop_index("idx_docforge_documents_user_id")
    op.drop_table("docforge_documents")
    op.drop_index("idx_docforge_folders_user_id")
    op.drop_table("docforge_folders")
    op.drop_index("idx_docforge_templates_user_id")
    op.drop_table("docforge_templates")
