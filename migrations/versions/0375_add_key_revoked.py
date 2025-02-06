"""

Revision ID: 7e8321806f71
Revises: 0375_add_key_revoked
Create Date: 2025-02-05 16:41:18.466800

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0375_add_key_revoked'
down_revision = '0374_add_expected_cadence'


def upgrade():
    op.add_column('api_keys', sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('api_keys_history', sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('api_keys_history', 'revoked')
    op.drop_column('api_keys', 'revoked')
