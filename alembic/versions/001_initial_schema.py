"""Initial schema with complete database structure.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-01-01 00:00:00.000000

This migration creates all tables matching the existing Supabase schema.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables."""
    
    # Create custom types (enums)
    user_role = postgresql.ENUM('admin', 'user', name='user_role', create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)
    
    auth_provider = postgresql.ENUM('google', 'credentials', name='auth_provider', create_type=False)
    auth_provider.create(op.get_bind(), checkfirst=True)
    
    source_type = postgresql.ENUM('pdf', 'image', 'text', 'excel', 'csv', 'document', 'other', name='source_type', create_type=False)
    source_type.create(op.get_bind(), checkfirst=True)
    
    generation_status = postgresql.ENUM('pending', 'processing', 'completed', 'error', name='generation_status', create_type=False)
    generation_status.create(op.get_bind(), checkfirst=True)
    
    export_format = postgresql.ENUM('docx', 'txt', 'pdf', 'png', name='export_format', create_type=False)
    export_format.create(op.get_bind(), checkfirst=True)
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('role', user_role, nullable=False, server_default='user'),
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auth_provider', auth_provider, nullable=False, server_default='credentials'),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Datasets table
    op.create_table(
        'datasets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_datasets_user_id', 'datasets', ['user_id'])
    
    # Input sources table
    op.create_table(
        'input_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dataset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', source_type, nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_input_sources_user_id', 'input_sources', ['user_id'])
    op.create_index('idx_input_sources_user_dataset', 'input_sources', ['user_id', 'dataset_id'])
    
    # Response formats table
    op.create_table(
        'response_formats',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template_text', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_response_formats_user', 'response_formats', ['user_id'])
    
    # Prompt folders table
    op.create_table(
        'prompt_folders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_prompt_folders_user', 'prompt_folders', ['user_id'])
    
    # Prompts table
    op.create_table(
        'prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('folder_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('prompt_folders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('response_format_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('response_formats.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_prompts_user', 'prompts', ['user_id'])
    op.create_index('idx_prompts_folder', 'prompts', ['folder_id'])
    
    # Prompt chains table
    op.create_table(
        'prompt_chains',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_prompt_chains_user', 'prompt_chains', ['user_id'])
    
    # Prompt chain steps table
    op.create_table(
        'prompt_chain_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('chain_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('prompt_chains.id', ondelete='CASCADE'), nullable=False),
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('prompts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('response_format_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('response_formats.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('chain_id', 'step_order', name='uq_chain_step_order'),
    )
    op.create_index('idx_chain_steps_chain_id', 'prompt_chain_steps', ['chain_id'])
    
    # Generations table
    op.create_table(
        'generations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('response_format_text', sa.Text(), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=False),
        sa.Column('response_content', sa.Text(), nullable=True),
        sa.Column('status', generation_status, nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('prompt_chain_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('prompt_chains.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_generations_user_id', 'generations', ['user_id'])
    op.create_index('idx_generations_status', 'generations', ['status'])
    
    # Generation sources junction table
    op.create_table(
        'generation_sources',
        sa.Column('generation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('generations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('input_sources.id', ondelete='CASCADE'), primary_key=True),
    )
    
    # Exported documents table
    op.create_table(
        'exported_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('generation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('generations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('format', export_format, nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_exported_documents_user_id', 'exported_documents', ['user_id'])
    op.create_index('idx_exported_documents_generation_id', 'exported_documents', ['generation_id'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('exported_documents')
    op.drop_table('generation_sources')
    op.drop_table('generations')
    op.drop_table('prompt_chain_steps')
    op.drop_table('prompt_chains')
    op.drop_table('prompts')
    op.drop_table('prompt_folders')
    op.drop_table('response_formats')
    op.drop_table('input_sources')
    op.drop_table('datasets')
    op.drop_table('users')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS export_format')
    op.execute('DROP TYPE IF EXISTS generation_status')
    op.execute('DROP TYPE IF EXISTS source_type')
    op.execute('DROP TYPE IF EXISTS auth_provider')
    op.execute('DROP TYPE IF EXISTS user_role')
