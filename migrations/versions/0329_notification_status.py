"""

Revision ID: 0329_notification_status
Revises: 0328_identity_provider_user_id
Create Date: 2021-05-07

"""
from alembic import op
import sqlalchemy as sa

from app.models import NOTIFICATION_STATUS_TYPES_COMPLETED

revision = '0329_notification_status'
down_revision = '0328_identity_provider_user_id'


def upgrade():
    op.add_column('service_callback_api', sa.Column(
        'notification_statuses', sa.String(length=255), nullable=False, default=str(NOTIFICATION_STATUS_TYPES_COMPLETED)
    ))
    op.add_column('service_callback_api_history', sa.Column(
        'notification_statuses', sa.String(length=255), nullable=True
    ))


def downgrade():
    op.drop_column('service_callback_api', 'notification_statuses')
    op.drop_column('service_callback_api_history', 'notification_statuses')
