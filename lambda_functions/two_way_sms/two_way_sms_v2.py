# imports
import logging
import psycopg2

# Global Variables
TWO_WAY_SMS_TABLE_DICT = {}
START_TYPES = []
STOP_TYPES = []
HELP_TYPES = []
logger = None

# Handle all intitialization of the lambda execution environemnt and logic


def two_way_v2_handler(event: dict, context, worker_id=None):
    global TWO_WAY_SMS_TABLE_DICT, logger
    initialize_invocation()
    try:
        aws_number = event['originationNumber']
        if not TWO_WAY_SMS_TABLE_DICT[aws_number]['service_managed']:
            process_message()
    except Exception as e:
        logger.exception(e)
    pass

def initialize_invocation() -> None:
    """
    Sets and checks anything that could not be set/checked during the invocation environment. 
    Also calls validation for the event.
    """
    global logger
    logger = logging.getLogger("TwoWaySMSv2")
    logger.setLevel(logging.INFO)

    validate_event()
    set_service_two_way_sms_table()
    pass

def validate_event() -> None:
    """
    Ensure the event has all the necessary fields
    """
    
    pass

def set_service_two_way_sms_table() -> None:
    """
    Sets the TWO_WAY_SMS_TABLE_DICT if it is not set by opening a connection to the DB and 
    querying the table.
    """
    global TWO_WAY_SMS_TABLE_DICT
    # format for dict should be set to {'number':{'service_id': <value>, 'destination_url': <value>, 'service_managed': <value> }}
    db_connection = make_database_connection()
    pass

def process_message(message: str):
    """
    Parses the string to look for start, stop, or help key words and handles those.
    """
    pass

def make_database_connection(worker_id:int = None) -> psycopg2.connection:
    """
    Return a connection to the database, or return None.

    https://www.psycopg.org/docs/module.html#psycopg2.connect
    https://www.psycopg.org/docs/module.html#exceptions
    """

    connection = None

    try:
        logger.debug("Connecting to the database . . .")
        connection = psycopg2.connect(sqlalchemy_database_uri + ('' if worker_id is None else f"_{worker_id}"))
        logger.debug(". . . Connected to the database.")
    except psycopg2.Warning as e:
        logger.warning(e)
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)

    return connection

