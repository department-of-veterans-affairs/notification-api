"""

Revision ID: 1b2cc88d9bc4
Revises: 0367_add_auth_parameter
Create Date: 2024-02-23 15:38:28.707461

"""
from alembic import op
import sqlalchemy as sa

revision = '0368_junk'
down_revision = '0367_add_auth_parameter'


def upgrade():
    op.add_column('notification_failures', sa.Column('junk', sa.String(length=1), nullable=True))


def downgrade():
    op.drop_column('notification_failures', 'junk')
