"""
Revision ID: 11414710f61a
Revises: 0351_user_service_roles
Create Date: 2022-11-02 19:54:18.568514
"""

from alembic import op
from sqlalchemy import func
from sqlalchemy.dialects import postgresql

revision = '0352_default_value_added_to_updated_at'
down_revision = '0351_user_service_roles'


def upgrade():
    op.alter_column(
        'provider_details',
        'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        existing_nullable=True,
        nullable=False,
        server_default=func.now()
    )
    op.alter_column(
        'provider_details_history',
        'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        existing_nullable=True,
        nullable=False,
        server_default=func.now()
    )


def downgrade():
    op.alter_column(
        'provider_details_history',
        'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        existing_nullable=False,
        nullable=True
    )
    op.alter_column(
        'provider_details',
        'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        existing_nullable=False,
        nullable=True
    )
