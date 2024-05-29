"""

Revision ID:0369_vaprofile_cache_fields
Revises: 0368_servicesmssender_columns
Create Date: 2024-05-29 10:55:37

"""
from alembic import op
import sqlalchemy as sa

revision = '0369_va_profile_cache_fields'
down_revision = '0368_servicesmssender_columns'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('va_profile_local_cache', sa.Column('participant_id', sa.Integer(), nullable=True))
    op.add_column('va_profile_local_cache', sa.Column('has_duplicate_mappings', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('va_profile_local_cache', 'has_duplicate_mappings')
    op.drop_column('va_profile_local_cache', 'participant_id')
    # ### end Alembic commands ###
