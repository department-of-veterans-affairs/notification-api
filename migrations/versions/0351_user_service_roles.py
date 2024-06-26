"""

Revision ID: 0351_user_service_roles
Revises: 0350_add_sms_sender_service_id
Create Date: 2022-08-02 13:49:30.137873

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0351_user_service_roles'
down_revision = '0350_add_sms_sender_service_id'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_service_roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=255), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_service_roles_service_id'), 'user_service_roles', ['service_id'], unique=False)
    op.create_index(op.f('ix_user_service_roles_user_id'), 'user_service_roles', ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_service_roles_user_id'), table_name='user_service_roles')
    op.drop_index(op.f('ix_user_service_roles_service_id'), table_name='user_service_roles')
    op.drop_table('user_service_roles')
    # ### end Alembic commands ###
