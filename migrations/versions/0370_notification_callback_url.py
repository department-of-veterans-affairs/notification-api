"""
Revision ID: 5deab283266f
Revises: 0369a_va_profile_cache_fields
Create Date: 2024-10-01 19:12:54.511134
"""

from alembic import op
import sqlalchemy as sa

revision = '5deab283266f'
down_revision = '0369a_va_profile_cache_fields'


def upgrade():
    op.add_column('notifications', sa.Column('callback_url', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('notifications', 'callback_url')
