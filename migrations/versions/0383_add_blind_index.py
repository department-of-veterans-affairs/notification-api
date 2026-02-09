"""

Revision ID: 0383_add_blind_index
Revises: 0382_add_cache_encryption
Create Date: 2026-02-09 19:11:25.738331

"""
from alembic import op
import sqlalchemy as sa

revision = '0383_add_blind_index'
down_revision = '0382_add_cache_encryption'


def upgrade():
    op.add_column('va_profile_local_cache', sa.Column('encrypted_va_profile_id_blind_index', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('va_profile_local_cache', 'encrypted_va_profile_id_blind_index')
