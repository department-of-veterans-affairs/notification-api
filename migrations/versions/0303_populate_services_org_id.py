"""

Revision ID: 0303_populate_services_org_id
Revises: 0302_add_org_id_to_services
Create Date: 2019-08-06 09:43:57.993510

"""
from alembic import op
import sqlalchemy as sa

revision = '0303_populate_services_org_id'
down_revision = '0302_add_org_id_to_services'


def upgrade():
    conn = op.get_bind()
    results = conn.execute(sa.text("select service_id, organisation_id from organisation_to_service"))
    org_to_service = results.fetchall()
    for x in org_to_service:
        sql = f"""
            UPDATE services
            SET organisation_id = {x.organisation_id}
            WHERE id = {x.service_id}
        """
        conn.execute(sa.text(sql))
        history_sql = f"""
            UPDATE services_history
            SET organisation_id = {x.organisation_id}
            WHERE id = {x.service_id}
              AND version = (select max(version) from services_history sh2 where id = services_history.id); 
        """
        conn.execute(sa.text(history_sql))


def downgrade():
    conn = op.get_bind()

    results = conn.execute(sa.text("select id, organisation_id from services where organisation_id is not null"))
    services = results.fetchall()
    results_2 = conn.execute(sa.text("select service_id, organisation_id from organisation_to_service"))
    org_to_service = results_2.fetchall()

    for x in services:
        os = [y for y in org_to_service if y.service_id == x.id]
        if len(os) == 1:
            update_sql = f"""
                UPDATE organisation_to_service
                SET organisation_id = {x.organisation_id}
                WHERE service_id = {x.id}
            """
            conn.execute(sa.text(update_sql))
        elif len(os) == 0:
            insert_sql = f"""
                INSERT INTO organisation_to_service(service_id, organisation_id) VALUES({x.id}, {x.organisation_id}
            """
            conn.execute(sa.text(insert_sql))
        else:
            raise Exception("should only have 1 row. Service_id {},  orgid: {}".format(x.id, x.organisation_id))
