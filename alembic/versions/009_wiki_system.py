"""Add LLM Wiki system tables.

Revision ID: 009_wiki_system
Revises: 008_docforge
Create Date: 2026-04-13
"""
from alembic import op

# revision identifiers
revision = "009_wiki_system"
down_revision = "008_docforge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──
    op.execute("""DO $$ BEGIN CREATE TYPE wiki_page_type AS ENUM (
        'entity','concept','source_summary','topic_summary',
        'comparison','analysis','index','overview'
    ); EXCEPTION WHEN duplicate_object THEN NULL; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE wiki_log_operation AS ENUM (
        'ingest','query','lint','transform',
        'update','create_page','delete_page'
    ); EXCEPTION WHEN duplicate_object THEN NULL; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE wiki_transformation_type AS ENUM (
        'concept_map','qa_exercises','story','podcast_transcript',
        'video_script','flashcards','quiz','slide_deck',
        'mind_map','character_story','advanced_summary','comparison_table'
    ); EXCEPTION WHEN duplicate_object THEN NULL; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE wiki_transformation_status AS ENUM (
        'pending','processing','completed','error'
    ); EXCEPTION WHEN duplicate_object THEN NULL; END $$""")

    # ── wikis ──
    op.execute("""CREATE TABLE IF NOT EXISTS wikis (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        schema_config JSONB NOT NULL DEFAULT '{}',
        stats JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_wikis_user_dataset UNIQUE (user_id, dataset_id)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wikis_user_id ON wikis (user_id)")

    # ── wiki_pages ──
    op.execute("""CREATE TABLE IF NOT EXISTS wiki_pages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        wiki_id UUID NOT NULL REFERENCES wikis(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        slug TEXT NOT NULL,
        page_type wiki_page_type NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        frontmatter JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_wiki_pages_wiki_slug UNIQUE (wiki_id, slug)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_wiki_id ON wiki_pages (wiki_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_type ON wiki_pages (page_type)")

    # Full-text search
    op.execute("""ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(content, '')), 'B')
        ) STORED""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_search ON wiki_pages USING GIN (search_vector)")

    # ── wiki_page_links ──
    op.execute("""CREATE TABLE IF NOT EXISTS wiki_page_links (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
        target_page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
        link_text TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_wiki_page_links_src_tgt UNIQUE (source_page_id, target_page_id)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_page_links_source ON wiki_page_links (source_page_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_page_links_target ON wiki_page_links (target_page_id)")

    # ── wiki_source_pages ──
    op.execute("""CREATE TABLE IF NOT EXISTS wiki_source_pages (
        source_id UUID NOT NULL REFERENCES input_sources(id) ON DELETE CASCADE,
        page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
        PRIMARY KEY (source_id, page_id)
    )""")

    # ── wiki_logs ──
    op.execute("""CREATE TABLE IF NOT EXISTS wiki_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        wiki_id UUID NOT NULL REFERENCES wikis(id) ON DELETE CASCADE,
        operation wiki_log_operation NOT NULL,
        summary TEXT NOT NULL,
        details JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_logs_wiki_created ON wiki_logs (wiki_id, created_at)")

    # ── wiki_transformations ──
    op.execute("""CREATE TABLE IF NOT EXISTS wiki_transformations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        wiki_id UUID NOT NULL REFERENCES wikis(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        transformation_type wiki_transformation_type NOT NULL,
        scope JSONB NOT NULL DEFAULT '{}',
        content TEXT NOT NULL DEFAULT '',
        config JSONB NOT NULL DEFAULT '{}',
        status wiki_transformation_status NOT NULL DEFAULT 'pending',
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wiki_transformations_wiki_type ON wiki_transformations (wiki_id, transformation_type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wiki_transformations CASCADE")
    op.execute("DROP TABLE IF EXISTS wiki_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS wiki_source_pages CASCADE")
    op.execute("DROP TABLE IF EXISTS wiki_page_links CASCADE")
    op.execute("DROP TABLE IF EXISTS wiki_pages CASCADE")
    op.execute("DROP TABLE IF EXISTS wikis CASCADE")
    op.execute("DROP TYPE IF EXISTS wiki_transformation_status")
    op.execute("DROP TYPE IF EXISTS wiki_transformation_type")
    op.execute("DROP TYPE IF EXISTS wiki_log_operation")
    op.execute("DROP TYPE IF EXISTS wiki_page_type")
