"""

Revision ID: 9b0fc64138c1
Revises: 0367_add_auth_parameter
Create Date: 2024-02-14 19:28:27.148482

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0368_add_id_ft_notify_status'
down_revision = '0367_add_auth_parameter'


def upgrade():
    op.add_column('ft_notification_status', sa.Column('id', postgresql.UUID(as_uuid=True)))
    op.execute('ALTER TABLE ft_notification_status DROP CONSTRAINT ft_notification_status_pkey;')
    op.execute('UPDATE ft_notification_status SET id = uuid_generate_v4();')
    op.create_primary_key('ft_notification_status_pkey', 'ft_notification_status', ['id'])
    op.create_unique_constraint(
        'uix_fact_notification_status',
        'ft_notification_status',
        ['bst_date', 'template_id', 'service_id', 'job_id', 'notification_type', 'key_type', 'notification_status'],
    )


def downgrade():
    op.drop_constraint('uix_fact_notification_status', 'ft_notification_status', type_='unique')
    op.drop_column('ft_notification_status', 'id')
    op.create_primary_key(
        'ft_notification_status_pkey',
        'ft_notification_status',
        [
            'bst_date',
            'template_id',
            'service_id',
            'job_id',
            'notification_type',
            'key_type',
            'notification_status',
            'status_reason',
        ],
    )
