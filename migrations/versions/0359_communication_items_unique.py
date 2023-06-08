"""
Revision ID: 0359_communication_items_unique
Revises: 0358_default_send_field
Create Date: 2023-06-07 21:53:38.930162
"""

from alembic import op
import sqlalchemy as sa

revision = "0359_communication_items_unique"
down_revision = "0358_default_send_field"


def upgrade():
    op.alter_column(
        "communication_items", "name",
        existing_type=sa.VARCHAR(),
        type_=sa.Text(),
        existing_nullable=False
    )
    op.create_unique_constraint("communication_items_unique_name", "communication_items", ["name"])
    op.create_unique_constraint(
        "communication_items_unique_va_profile_item_id",
        "communication_items",
        ["va_profile_item_id"]
    )


def downgrade():
    # op.drop_constraint("communication_items_unique_va_profile_item_id", "communication_items", type_="unique")
    # op.drop_constraint("communication_items_unique_name", "communication_items", type_="unique")
    # TODO - These names are the ones automatically created.  Delete them after the downgrade.
    op.drop_constraint("communication_items_va_profile_item_id_key", "communication_items", type_="unique")
    op.drop_constraint("communication_items_name_key", "communication_items", type_="unique")
    op.alter_column(
        "communication_items", "name",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(),
        existing_nullable=False
    )
