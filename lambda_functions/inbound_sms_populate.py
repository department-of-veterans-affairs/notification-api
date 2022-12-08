import logging
from sqlalchemy import create_engine
from datetime import datetime

logger = logging.getLogger("incoming_inbound_sms_lambda_handler")
logger.setLevel(logging.INFO)


def incoming_inbound_sms_lambda_handler(event, context):
    try:
        logger.debug(event)
    except Exception as e:
        logger.error(event)
        logger.exception(e)


def insert_db_record(data):
    """ Connect to the PostgreSQL database server """
    try:
        # connect to the PostgreSQL server
        logger.debug('Connecting to the PostgreSQL database...')
        db_string = "postgresql://postgres:LocalPassword@localhost:5432/notification_api"
        db = create_engine(db_string)

        # ----------------------- SQL --------------------
        # --- INSERT
        sql = f"INSERT INTO inbound_sms VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        db.execute(sql, (data['id'], data['service_id'], data['content'], data['notify_number'], data['user_number'], data['created_at'], data['provider_date'], data['provider_reference'], data['provider']))

        # --- Read
        # results = db.execute("SELECT * FROM inbound_sms")
        # for row in results:
        #     print(row)

        # --- Delete
        # query = f"DELETE FROM {table} WHERE id=%s"
        # db.execute(query, data['id'])

    except Exception as error:
        logger.error(error)
    finally:
        logger.debug('Database connection closed.')
