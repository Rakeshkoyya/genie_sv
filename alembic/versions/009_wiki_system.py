"""Stub for missing 009_wiki_system migration.

This file was recreated because the original was lost.
The schema changes it applied are already present in the database.
"""
from alembic import op

revision = "009_wiki_system"
down_revision = "008_docforge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema already applied to DB — no-op stub
    pass


def downgrade() -> None:
    pass
