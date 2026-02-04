"""

Revision ID: 0382_add_cache_encryption
Revises: 0381_add_retry_fields
Create Date: 2026-02-03 20:19:49.738331

"""
from alembic import op
import sqlalchemy as sa

revision = '0382_add_cache_encryption'
down_revision = '0381_add_retry_fields'


def upgrade():
    op.add_column('va_profile_local_cache', sa.Column('encrypted_va_profile_id', sa.Text(), nullable=True))
    op.add_column('va_profile_local_cache', sa.Column('encrypted_participant_id', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('va_profile_local_cache', 'encrypted_participant_id')
    op.drop_column('va_profile_local_cache', 'encrypted_va_profile_id')
