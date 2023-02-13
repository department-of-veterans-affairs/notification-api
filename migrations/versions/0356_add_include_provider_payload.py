"""

Revision ID: 0356_add_include_provider_payload
Revises: 0355_sms_billing
Create Date: 2023-02-13 16:37:56.265491

"""
from alembic import op
import sqlalchemy as sa

revision = '0356_add_include_provider_payload'
down_revision = '0355_sms_billing'


def upgrade():
    op.add_column('service_callback', sa.Column('include_provider_payload', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('service_callback_history', sa.Column('include_provider_payload', sa.Boolean(), nullable=False, server_default='0'))

    # TODO migration - remove these lines before merging
    # unnecessary extra stuff
    # op.alter_column('service_callback', 'bearer_token',
    #            existing_type=sa.VARCHAR(),
    #            nullable=False)
    # op.drop_index('ix_service_callback_api_service_id', table_name='service_callback')
    # op.drop_index('ix_service_callback_api_updated_by_id', table_name='service_callback')
    # op.create_index(op.f('ix_service_callback_service_id'), 'service_callback', ['service_id'], unique=False)
    # op.create_index(op.f('ix_service_callback_updated_by_id'), 'service_callback', ['updated_by_id'], unique=False)
    # op.create_unique_constraint('uix_service_callback_channel', 'service_callback', ['service_id', 'callback_channel'])
    # op.alter_column('service_callback_history', 'bearer_token',
    #            existing_type=sa.VARCHAR(),
    #            nullable=False)
    # op.drop_index('ix_service_callback_api_history_service_id', table_name='service_callback_history')
    # op.drop_index('ix_service_callback_api_history_updated_by_id', table_name='service_callback_history')
    # op.create_index(op.f('ix_service_callback_history_service_id'), 'service_callback_history', ['service_id'], unique=False)
    # op.create_index(op.f('ix_service_callback_history_updated_by_id'), 'service_callback_history', ['updated_by_id'], unique=False)


def downgrade():
    op.drop_column('service_callback', 'include_provider_payload')
    op.drop_column('service_callback_history', 'include_provider_payload')

    # TODO migration - remove these lines before merging
    # unnecessary stuff
    # op.drop_index(op.f('ix_service_callback_history_updated_by_id'), table_name='service_callback_history')
    # op.drop_index(op.f('ix_service_callback_history_service_id'), table_name='service_callback_history')
    # op.create_index('ix_service_callback_api_history_updated_by_id', 'service_callback_history', ['updated_by_id'], unique=False)
    # op.create_index('ix_service_callback_api_history_service_id', 'service_callback_history', ['service_id'], unique=False)
    # op.alter_column('service_callback_history', 'bearer_token',
    #            existing_type=sa.VARCHAR(),
    #            nullable=True)
    # op.drop_constraint('uix_service_callback_channel', 'service_callback', type_='unique')
    # op.drop_index(op.f('ix_service_callback_updated_by_id'), table_name='service_callback')
    # op.drop_index(op.f('ix_service_callback_service_id'), table_name='service_callback')
    # op.create_index('ix_service_callback_api_updated_by_id', 'service_callback', ['updated_by_id'], unique=False)
    # op.create_index('ix_service_callback_api_service_id', 'service_callback', ['service_id'], unique=False)
    # op.alter_column('service_callback', 'bearer_token',
    #            existing_type=sa.VARCHAR(),
    #            nullable=True)
