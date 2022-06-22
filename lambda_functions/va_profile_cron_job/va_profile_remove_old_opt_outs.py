import logging
import os
import psycopg2
import sys

REMOVE_OPTED_OUT_RECORDS_QUERY = """SELECT va_profile_remove_old_opt_outs();"""
SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")

if SQLALCHEMY_DATABASE_URI is None:
    logging.error("The database URI is not set.")
    sys.exit("Couldn't connect to the database.")

db_connection = None


def make_connection(worker_id):
    """
    Return a connection to the database, or return None.
    """

    connection = None

    # https://www.psycopg.org/docs/module.html#exceptions
    try:
        connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f"_{worker_id}"))
    except psycopg2.Warning as e:
        logging.warning(e)
    except psycopg2.Error as e:
        logging.exception(e)
        logging.error(e.pgcode)

    return connection


def va_profile_remove_old_opt_outs_handler(event, context, worker_id=None):
    """This function deletes any va_profile cache records that are opted out."""

    if db_connection is None or db_connection.status != 0:
        # Attempt to (re-)establish a database connection
        db_connection = make_connection(worker_id)

    if db_connection is None:
        raise RuntimeError("No database connection.")

    try:
        with db_connection.cursor() as c:
            c.execute(REMOVE_OPTED_OUT_RECORDS_QUERY)
            db_connection.commit()
    except Exception as e:
        logging.exception(e)