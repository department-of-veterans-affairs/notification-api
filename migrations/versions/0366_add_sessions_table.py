"""

Revision ID: 6392698ad84a
Revises: 0365_add_notification_failures
Create Date: 2023-11-30 21:40:23.546531

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0366_add_sessions_table'
down_revision = '0365_add_notification_failures'


def upgrade():
    op.create_table('sessions',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    op.create_index('index_sessions_on_session_id', 'sessions', ['session_id'], unique=True)
    op.create_index('index_sessions_on_updated_at', 'sessions', ['updated_at'])

def downgrade():
    op.drop_index('index_session_updated_at', table_name='sessions')
    op.drop_index('unique_session_id', table_name='sessions')
    op.drop_table('sessions')