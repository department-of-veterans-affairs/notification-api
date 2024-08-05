"""

Revision ID: bab2a5de15d8
Revises: 0369_va_profile_cache_fields
Create Date: 2024-08-05 15:10:01.963467

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'bab2a5de15d8'
down_revision = '0369a_va_profile_cache_fields'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('va_profile_local_cache', 'va_profile_id',
               existing_type=sa.INTEGER(),
               type_=sa.BigInteger(),
               existing_nullable=False)
    op.alter_column('va_profile_local_cache', 'participant_id',
               existing_type=sa.INTEGER(),
               type_=sa.BigInteger(),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('va_profile_local_cache', 'participant_id',
               existing_type=sa.BigInteger(),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('va_profile_local_cache', 'va_profile_id',
               existing_type=sa.BigInteger(),
               type_=sa.INTEGER(),
               existing_nullable=False)
    # ### end Alembic commands ###
