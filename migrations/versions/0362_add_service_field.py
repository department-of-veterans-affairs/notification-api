"""

Revision ID: 0362_add_service_field
Revises: 0361_remove_letter_branding
Create Date: 2023-09-08 11:01:59.093025

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0362_add_service_field'
down_revision = '0361_remove_letter_branding'


def upgrade():
    op.add_column('services', sa.Column('p2p_enabled', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('services', 'p2p_enabled')
