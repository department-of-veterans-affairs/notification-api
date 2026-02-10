"""

Revision ID: 0384_test_timeout_enforcement
Revises: 0383_add_blind_index
Create Date: 2026-02-10 18:45:55.960614

"""
from alembic import op
import sqlalchemy as sa


revision = '0384_test_timeout_enforcement'
down_revision = '0383_add_blind_index'


def upgrade():
    op.execute("SELECT pg_sleep(20)")


def downgrade():
    pass
