"""
Revision ID: 0381_add_retry_fields
Revises: 0380_add_service_allow_fallback
Create Date: 2026-01-06 22:39:28.498426
"""
from alembic import op
import sqlalchemy as sa


revision = '0381_add_retry_fields'
down_revision = '0380_add_service_allow_fallback'


def upgrade():
    op.add_column('notifications', sa.Column('retry_count', sa.Integer(), nullable=True))
    op.add_column('notifications', sa.Column('provider_updated_at', sa.DateTime(), nullable=True))
    op.add_column('notification_history', sa.Column('retry_count', sa.Integer(), nullable=True))
    op.add_column('notification_history', sa.Column('provider_updated_at', sa.DateTime(), nullable=True))

    op.execute('UPDATE notifications SET retry_count = 0')
    op.execute('UPDATE notification_history SET retry_count = 0')

    op.alter_column('notifications', 'retry_count', nullable=False, server_default='0')
    op.alter_column('notification_history', 'retry_count', nullable=False, server_default='0')


def downgrade():
    op.drop_column('notification_history', 'provider_updated_at')
    op.drop_column('notification_history', 'retry_count')
    op.drop_column('notifications', 'provider_updated_at')
    op.drop_column('notifications', 'retry_count')
