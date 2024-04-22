"""
Revision ID: 0368_servicesmssender_columns
Revises: 0367_add_auth_parameter
Create Date: 2024-04-22 14:20:28.054509
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0368_servicesmssender_columns'
down_revision = '0367_add_auth_parameter'


def upgrade():
    # Migration 0331 moved rows in the service_inbound_api table to other tables but erroneously didn't drop the table.
    # TODO - The migrations never drop this index, but it doesn't seem to exist in Dev.
    # op.drop_index('ix_service_inbound_api_service_id', table_name='service_inbound_api')
    # op.drop_index('ix_service_inbound_api_updated_by_id', table_name='service_inbound_api')
    # op.drop_table('service_inbound_api')

    op.add_column('service_sms_senders', sa.Column('description', sa.String(length=256), nullable=True))
    op.add_column('service_sms_senders', sa.Column('provider_id', postgresql.UUID(), nullable=True))
    op.create_foreign_key(None, 'service_sms_senders', 'provider_details', ['provider_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'service_sms_senders', type_='foreignkey')
    op.drop_column('service_sms_senders', 'provider_id')
    op.drop_column('service_sms_senders', 'description')

    # op.create_table('service_inbound_api',
    #     sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
    #     sa.Column('service_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #     sa.Column('url', sa.VARCHAR(), autoincrement=False, nullable=False),
    #     sa.Column('bearer_token', sa.VARCHAR(), autoincrement=False, nullable=False),
    #     sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    #     sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    #     sa.Column('updated_by_id', postgresql.UUID(), autoincrement=False, nullable=False),
    #     sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
    #     sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='service_inbound_api_service_id_fkey'),
    #     sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name='service_inbound_api_updated_by_id_fkey'),
    #     sa.PrimaryKeyConstraint('id', name='service_inbound_api_pkey')
    # )
    # op.create_index('ix_service_inbound_api_updated_by_id', 'service_inbound_api', ['updated_by_id'], unique=False)
    # op.create_index('ix_service_inbound_api_service_id', 'service_inbound_api', ['service_id'], unique=True)
