from datetime import datetime
import logging
from os import sys

import psycopg2

# Global Variables
TWO_WAY_SMS_TABLE_DICT = {}

# seed values, will be confirmed with UX/product
START_TYPES = ('START', 'BEGIN', 'RESTART', 'OPTIN',)  
STOP_TYPES = ('STOP', 'OPTOUT',)
HELP_TYPES = ('HELP',)
START_TEXT = "Message service resumed, reply \"STOP\" to stop receiving messages."
STOP_TEXT = "Message service stopped, reply \"START\" to start receiving messages."
HELP_TEXT = "Some help text"
logger = None

# Handle all intitialization of the lambda execution environemnt and logic


def two_way_v2_handler(event: dict, context, worker_id=None):
    global TWO_WAY_SMS_TABLE_DICT, logger
    initialize_invocation()
    event_data = get_event_data(event)
    two_way_record = TWO_WAY_SMS_TABLE_DICT[event_data['originationNumber']]

    try:
        # If the number is not self-managed, look for key words
        if not two_way_record['service_managed']:
            process_message(event_data['messageBody'])
    except Exception as e:
        logger.exception(e)

    

def initialize_invocation() -> None:
    """
    Sets and checks anything that could not be set/checked during the invocation environment. 
    Also calls validation for the event.
    """
    global logger
    try:
        logger = logging.getLogger("TwoWaySMSv2")
        logger.setLevel(logging.INFO)
    except Exception as e:
        sys.exit()

    validate_event()
    set_service_two_way_sms_table()
    pass

def get_event_data(event: dict) -> dict:
    """
    Parses the event to obtain sns data and put it into usable form
    """
    event_data = {}

    # Set dateRecevied if not reprocessing from SQS
    if 'dateRecevied' not in event_data:
        event_data['dateRecevied'] = datetime.utcnow()
    return event_data

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
    logger.debug(f'Message: {message}')

    message = message.upper()
    if message.startswith(START_TYPES):
        process_keyword(START_TEXT, "START")
    elif message.startswith(STOP_TYPES):
        process_keyword(STOP_TEXT, "STOP")
    elif message.startswith(HELP_TEXT):
        process_keyword(HELP_TEXT, "HELP")
    else:
        logger.info('No keywords detected...')

def process_keyword(reply_message: str, keyword_type: str) -> None:
    """
    Identification of a key word warrants sending a a message back to the sender. This method sends the correct
    message based on what was found in the user's message.
    """
    logger.info(f'Processing {keyword_type} from message...')
    # Not sure exactly how we will do that at the moment
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

