import logging
import os
from typing import final
import psycopg2
import sys

REMOVE_OPTED_OUT_RECORDS_QUERY = """SELECT va_profile_remove_old_opt_outs();"""
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

if SQLALCHEMY_DATABASE_URI is None:
    logger.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")

logger.info('Execution environment prepared...')


def va_profile_remove_old_opt_outs_handler(event=None, context=None, worker_id=None):
    """
    This function deletes any va_profile cache records that
    are opted out and greater than 24 hours old.
    """

    connection = None
    # https://www.psycopg.org/docs/module.html#exceptions
    try:
        connection = make_connetion(worker_id)
        logger.info('Connected to database...')
        with connection.cursor() as c:
            logger.info('Executing remove opt out function...')
            c.execute(REMOVE_OPTED_OUT_RECORDS_QUERY)
            logger.info('Committing to database...')
            connection.commit()
            logger.info('Commit to database...')
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)
    except Exception as e:
        logger.exception(e)
    finally:
        if connection:
            connection.close()
            logger.info('Connection to database closed...')

def make_connetion(worker_id):
    logger.info('Connecting to database...')
    return psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f"_{worker_id}"))
