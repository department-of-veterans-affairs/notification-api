"""

Revision ID: 0365_add_notification_failures
Revises: 0364_add_templatep2pchecklist.py
Create Date: 2023-11-01 15:23:30.268549

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0365_add_notification_failures"
down_revision = "0364_add_templatep2pchecklist"


def upgrade():
    op.create_table(
        "notification_failures",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True)),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("notification_id"),
    )


def downgrade():
    op.drop_table("notification_failures")
