"""
Revision ID: 0345_alter_VAProfileLocalCache
Revises: 0344_add_onsite_notification
Create Date: 2022-04-20 17.48:14.050637
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0345_alter_VAProfileLocalCache'
down_revision = '0344_add_onsite_notification'


def upgrade():
    op.add_column('va_profile_local_cache', sa.Column('communication_channel_id', sa.Integer(), nullable=False))
    op.alter_column('va_profile_local_cache', 'va_profile_item_id', new_column_name='communication_item_id')
    op.add_column('va_profile_local_cache', sa.Column('source_datetime', sa.DateTime(), nullable=True))
    op.add_column('va_profile_local_cache', sa.Column('allowed', sa.Boolean(), nullable=False))
    op.create_unique_constraint('uix_service_callback_channel', 'service_callback', ['service_id', 'callback_channel'])


def downgrade():
    op.alter_column('va_profile_local_cache', 'communication_item_id', new_column_name='va_profile_item_id')
    op.drop_column('va_profile_local_cache', 'communication_channel_id')
    op.drop_column('va_profile_local_cache', 'source_datetime')
    op.drop_column('va_profile_local_cache', 'allowed')
    op.drop_constraint('uix_veteran_id', 'va_profile_local_cache', type_='unique')

