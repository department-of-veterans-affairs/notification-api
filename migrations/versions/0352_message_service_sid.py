"""
Revision ID: 0352_message_service_sid
Revises: 0351_user_service_roles
Create Date: 2022-08-16 03:17:23.728949
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0352_message_service_sid'
down_revision = '0351_user_service_roles'


def upgrade():
    op.add_column('notifications', sa.Column('message_service_sid', sa.String(length=34), nullable=True))


def downgrade():
    op.drop_column('notifications', 'message_service_sid')
