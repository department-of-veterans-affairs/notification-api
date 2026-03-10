"""

Revision ID: 0384_add_callback_headers
Revises: 0383_add_blind_index
Create Date: 2026-02-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0384_add_callback_headers'
down_revision = '0383_add_blind_index'


def upgrade():
    op.add_column('service_callback', sa.Column('callback_headers', sa.String(), nullable=True))
    op.add_column('service_callback_history', sa.Column('callback_headers', sa.String(), nullable=True))
    op.add_column('notifications', sa.Column('callback_headers', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'callback_headers')
    op.drop_column('service_callback_history', 'callback_headers')
    op.drop_column('service_callback', 'callback_headers')
