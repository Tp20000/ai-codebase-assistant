"""Add chat sessions and messages tables

Revision ID: 001_chat_tables
Revises:
Create Date: 2025-07-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_chat_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create chat_sessions and chat_messages tables."""
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column(
            'project_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('projects.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_chat_sessions_id', 'chat_sessions', ['id'], unique=False
    )
    op.create_index(
        'ix_chat_sessions_project_user',
        'chat_sessions',
        ['project_id', 'user_id'],
        unique=False,
    )

    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'session_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('prompt_type', sa.String(50), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('sources', postgresql.JSON(), nullable=True),
        sa.Column('retrieval_time_ms', sa.Float(), nullable=True),
        sa.Column('llm_time_ms', sa.Float(), nullable=True),
        sa.Column('total_time_ms', sa.Float(), nullable=True),
        sa.Column('tokens_generated', sa.Integer(), nullable=True),
        sa.Column('context_tokens', sa.Integer(), nullable=True),
        sa.Column('cached', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_chat_messages_id', 'chat_messages', ['id'], unique=False
    )
    op.create_index(
        'ix_chat_messages_session_created',
        'chat_messages',
        ['session_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Drop chat tables."""
    op.drop_index('ix_chat_messages_session_created', table_name='chat_messages')
    op.drop_index('ix_chat_messages_id', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_chat_sessions_project_user', table_name='chat_sessions')
    op.drop_index('ix_chat_sessions_id', table_name='chat_sessions')
    op.drop_table('chat_sessions')
