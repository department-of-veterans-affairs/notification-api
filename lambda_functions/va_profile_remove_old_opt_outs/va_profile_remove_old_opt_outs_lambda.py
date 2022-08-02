import logging
import os
import psycopg2
import sys

logger = logging.getLogger("VAProfileRemoveOldOptOuts")
logger.setLevel(logging.DEBUG)

REMOVE_OPTED_OUT_RECORDS_QUERY = """SELECT va_profile_remove_old_opt_outs();"""
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")

if SQLALCHEMY_DATABASE_URI is None:
    logger.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")


def va_profile_remove_old_opt_outs_handler(event=None, context=None, worker_id=None):
    """
    This function deletes any va_profile cache records that
    are opted out and greater than 24 hours old.
    """

    logger.debug("Running va_profile_remove_old_opt_outs_handler")

    # https://www.psycopg.org/docs/module.html#exceptions
    try:
        connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f"_{worker_id}"))

        logger.debug(f"--- Connected to db: {SQLALCHEMY_DATABASE_URI}")

        with connection.cursor() as c:
            c.execute(REMOVE_OPTED_OUT_RECORDS_QUERY)
            connection.commit()
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)
    except Exception as e:
        logger.exception(e)

    logger.debug("Finished va_profile_remove_old_opt_outs_handler")
