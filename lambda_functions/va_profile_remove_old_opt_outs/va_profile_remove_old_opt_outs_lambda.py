import logging
import os
import psycopg2
import sys


# Set globals
REMOVE_OPTED_OUT_RECORDS_QUERY = """SELECT va_profile_remove_old_opt_outs();"""
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
CONNECTION = None

# Set logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def make_connection(worker_id=None) -> None:
    """
    Return a connection to the database, or return None.

    https://www.psycopg.org/docs/module.html#psycopg2.connect
    https://www.psycopg.org/docs/module.html#exceptions
    """

    global CONNECTION

    try:
        logger.info('Connecting to database...')
        CONNECTION = psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f"_{worker_id}"))
        logger.info('Connected to database...')
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)
    except Exception as e:
        logger.exception(f'Unexpected error: {e}')


# Set the connection in the execution environment
make_connection()

# Verify environment is setup correctly
if SQLALCHEMY_DATABASE_URI is None:
    logger.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")
elif CONNECTION is None:
    logger.error("The database connection is not set.")
    sys.exit("Couldn't connect to the database.")
else:
    logger.info('Execution environment prepared...')


def execute_remove_function(worker_id=None, is_retry: bool = False) -> None:
    """
    Executes the REMOVE_OPTED_OUT_RECORDS_QUERY statement and commits.

    Returns None 
    """
    global CONNECTION

    try:
        with CONNECTION.cursor() as c:
            logger.info('Executing remove opt out function...')
            c.execute(REMOVE_OPTED_OUT_RECORDS_QUERY)
            logger.info('Committing to database...')
            CONNECTION.commit()
            logger.info('Commit to database...')
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        # https://www.postgresql.org/docs/11/errcodes-appendix.html
        logger.error(e.pgcode)
        logger.error(f'Possible lost connection to database, {"retrying" if not is_retry else "aborting"}...')

        # Attempt to retry the connection and the execution
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
