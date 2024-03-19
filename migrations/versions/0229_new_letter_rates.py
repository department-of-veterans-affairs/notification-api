"""empty message

Revision ID: 0229_new_letter_rates
Revises: 0228_notification_postage

"""

revision = '0229_new_letter_rates'
down_revision = '0228_notification_postage'

from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa


START = datetime(2018, 9, 30, 23, 0)

NEW_RATES = [
    (uuid.uuid4(), START, 1, 0.30, False, 'second'),
    (uuid.uuid4(), START, 2, 0.35, True, 'second'),
    (uuid.uuid4(), START, 2, 0.35, False, 'second'),
    (uuid.uuid4(), START, 3, 0.40, True, 'second'),
    (uuid.uuid4(), START, 3, 0.40, False, 'second'),
    (uuid.uuid4(), START, 4, 0.45, True, 'second'),
    (uuid.uuid4(), START, 4, 0.45, False, 'second'),
    (uuid.uuid4(), START, 5, 0.50, True, 'second'),
    (uuid.uuid4(), START, 5, 0.50, False, 'second'),
    (uuid.uuid4(), START, 1, 0.56, True, 'first'),
    (uuid.uuid4(), START, 1, 0.56, False, 'first'),
    (uuid.uuid4(), START, 2, 0.61, True, 'first'),
    (uuid.uuid4(), START, 2, 0.61, False, 'first'),
    (uuid.uuid4(), START, 3, 0.66, True, 'first'),
    (uuid.uuid4(), START, 3, 0.66, False, 'first'),
    (uuid.uuid4(), START, 4, 0.71, True, 'first'),
    (uuid.uuid4(), START, 4, 0.71, False, 'first'),
    (uuid.uuid4(), START, 5, 0.76, True, 'first'),
    (uuid.uuid4(), START, 5, 0.76, False, 'first'),
]


def upgrade():
    conn = op.get_bind()

    sql = (
        "update letter_rates "
        f"set end_date='{START}' "
        "where rate != 0.30"
    )
    conn.execute(sa.text(sql))

    for id, start_date, sheet_count, rate, crown, post_class in NEW_RATES:
        sql = (
           "INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class) " 
           f"VALUES ({id}, '{start_date}', {sheet_count}, {rate}, {crown}, '{post_class})'"
        )


def downgrade():
    conn = op.get_bind()
    sql = (
        "delete from letter_rates "
        f"where start_date = '{START}'"
    )
    conn.execute(sa.text(sql))

    sql = (
        "update letter_rates "
        "set end_date = null "
        f"where end_date = '{START}'"
    )

    conn.execute(sa.text(sql))
