import logging
import os
from typing import final
import psycopg2
import sys


# Set globals
REMOVE_OPTED_OUT_RECORDS_QUERY = """SELECT va_profile_remove_old_opt_outs();"""
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")


# Set logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

if SQLALCHEMY_DATABASE_URI is None:
    logger.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")
else:
    logger.info('Execution environment prepared...')

connection = None

def make_connection(worker_id=None) -> None:
    """
    Return a connection to the database, or return None.

    https://www.psycopg.org/docs/module.html#psycopg2.connect
    https://www.psycopg.org/docs/module.html#exceptions
    """

    global connection

    try:
        logger.info('Connecting to database...')
        connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f"_{worker_id}"))
        logger.info('Connected to database...')
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)
    except Exception as e:
        logger.exception(f'Unexpected error: {e}')

def execute_remove_function(worker_id=None, is_retry: bool = False) -> None:
    """
    Executes the REMOVE_OPTED_OUT_RECORDS_QUERY statement and commits.

    Returns None 
    """
    global connection

    if not connection:
        logger.info('Failed to execute removal function, no connection...')
        return

    try:
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
        logger.error(f'Possible lost connection to database, {"retrying" if not is_retry else "aborting"}...')
        if not is_retry:
            make_connection(worker_id)
            execute_remove_function(worker_id, is_retry=True)
    except Exception as e:
        logger.error(f'Unexpected error')
        logger.exception(e)

def va_profile_remove_old_opt_outs_handler(event=None, context=None, worker_id=None):
    """
    This function deletes any va_profile cache records that
    are opted out and greater than 24 hours old.
    """

    # https://www.psycopg.org/docs/module.html#exceptions
    try:
        execute_remove_function(worker_id)
    except Exception as e:
        logger.exception(e)

make_connection()
