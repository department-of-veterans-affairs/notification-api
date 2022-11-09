import boto3
from botocore.client import BaseClient
from datetime import datetime
import logging
from os import sys, environ
import psycopg2
import requests


# Global Variables
# Immutable
START_TYPES = ('START', 'BEGIN', 'RESTART', 'OPTIN', 'OPT-IN',)
STOP_TYPES = ('STOP', 'OPTOUT', 'OPT-OUT',)
HELP_TYPES = ('HELP',)
START_TEXT = 'Message service resumed, reply "STOP" to stop receiving messages.'
STOP_TEXT = 'Message service stopped, reply "START" to start receiving messages.'
HELP_TEXT = 'Some help text'
INBOUND_NUMBERS_QUERY = """SELECT number, service_id, url_endpoint, self_managed FROM inbound_numbers;"""
# Validation set
EXPECTED_SNS_FIELDS = set({'originationNumber',
                           'destinationNumber',
                           'messageKeyword',
                           'messageBody',
                           'inboundMessageId',
                           'previousPublishedMessageId',
                           })

# Pre-Configurable
AWS_PINPOINT_APP_ID = ''
AWS_REGION = ''
LOG_LEVEL = 'INFO'
SQLALCHEMY_DATABASE_URI = ''
TIMEOUT = 3

# Set within lambda
logger = None
AWS_PINPOINT = None
TWO_WAY_SMS_TABLE_DICT = {}


def set_env_variables() -> None:
    """
    Attempt to get environmental variables. Abort execution environment on failure.
    """
    global AWS_PINPOINT_APP_ID, AWS_REGION, LOG_LEVEL, SQLALCHEMY_DATABASE_URI, TIMEOUT

    try:
        AWS_PINPOINT_APP_ID = environ['aws_pinpoint_app_id']
        AWS_REGION = environ['aws_region']
        LOG_LEVEL = environ['log_level']
        SQLALCHEMY_DATABASE_URI = environ['sql_alchemy_database_uri']
        TIMEOUT = environ['timeout']
    except KeyError as e:
        sys.exit(f'Failed to find env variable: {e}')


def set_logger() -> None:
    global logger
    try:
        logger = logging.getLogger('TwoWaySMSv2')
        logger.setLevel(logging.getLevelName(LOG_LEVEL))
    except Exception as e:
        sys.exit('Logger failed to setup properly')


def make_database_connection(worker_id: int = None) -> psycopg2.connection:
    """
    Return a connection to the database, or return None.

    https://www.psycopg.org/docs/module.html#psycopg2.connect
    https://www.psycopg.org/docs/module.html#exceptions
    """
    try:
        logger.debug('Connecting to the database . . .')
        connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI + ('' if worker_id is None else f'_{worker_id}'))
        logger.info('. . . Connected to the database.')
    except psycopg2.Warning as e:
        logger.warning(e)
        raise
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)
        raise

    return connection


def set_service_two_way_sms_table() -> None:
    """
    Sets the TWO_WAY_SMS_TABLE_DICT if it is not set by opening a connection to the DB and 
    querying the table. This table should be small (a few dozen records at most).
    """
    # format for dict should be set to {'number':{'service_id': <value>, 'url_endpoint': <value>, 'self_managed': <value> }}
    global TWO_WAY_SMS_TABLE_DICT
    try:
        db_connection = make_database_connection()
        data = {}
        with db_connection.cursor() as c:
            # https://www.psycopg.org/docs/cursor.html#cursor.execute
            c.execute(INBOUND_NUMBERS_QUERY)
            data = c.fetchall()
            logger.debug(f'Data returned from query: {data}')
        db_connection.close()

        TWO_WAY_SMS_TABLE_DICT = {n: {'service_id': s,
                                      'url_endpoint': u,
                                      'self_managed': True if sm == 't' else False} for n, s, u, sm in data}
        logger.info('TWO_WAY_SMS_TABLE_DICT set...')
        logger.debug(f'Two way table as a dictionary with numbers as keys: {TWO_WAY_SMS_TABLE_DICT}')
    except Exception as e:
        logger.critical(f'Failed to query database: {e}')
        if db_connection:
            db_connection.close()
        sys.exit('Unable to load inbound_numbers table into dictionary')


def init_execution_environment() -> None:
    set_env_variables()
    set_logger()
    set_service_two_way_sms_table()
    logger.info('Execution environment setup...')


init_execution_environment()
# ------------------------------------ End Execution Environment Setup ------------------------------------

# ------------------------------------------- Begin Invocation --------------------------------------------


def two_way_sms_v2_handler(event: dict, context, worker_id=None):
    if not valid_event():
        push_to_dead_letter(event)
        return 500, 'Unrecognized event'

    if not set_aws_pinpoint():
        push_to_sqs(event)
        return 400, 'Failed to setup Pinpoint client'

    for event_data in event.get('Records'):
        inbound_sms = event_data.get('Sns')
        try:
            # Update and log SNS or SQS inbound_sms
            if 'dateReceived' not in event:
                logger.info('Processing SNS event...')
                inbound_sms['dateReceived'] = datetime.utcnow()
            else:
                logger.info('Processing SQS event...')

            # Unsafe lookup intentional to catch missing record
            two_way_record = TWO_WAY_SMS_TABLE_DICT[inbound_sms.get('originationNumber')]

            # If the number is not self-managed, look for key words
            if not two_way_record.get('self_managed'):
                logger.info('Service is not self-managed')
                keyword_phrase = detected_keyword(inbound_sms.get('messageBody', ''))
                if keyword_phrase:
                    send_message(two_way_record.get('destinationNumber', ''),
                                 two_way_record.get('originationNumber', ''),
                                 keyword_phrase)

            # Forward inbound_sms to associated service
            logger.info(f'Forwarding inbound SMS to service: {two_way_record.get("service_id")}')
            send_to_service(inbound_sms)
        except KeyError as e:
            logger.exception(e)
            logger.critical(f'Unable to find two_way_record for: {inbound_sms.get("originationNumber")}')
            push_to_dead_letter(inbound_sms)
        except Exception as e:
            logger.exception(e)
            push_to_sqs(inbound_sms)
    return 200, 'Success'


def valid_event(event_data: dict) -> bool:
    """
    Ensure the event has all the necessary fields
    """
    if 'Records' in event_data:
        for event in event_data.get('Records'):
            inbound_sms = event.get('Sns')
            if not inbound_sms or not EXPECTED_SNS_FIELDS.issubset(inbound_sms):
                logger.critical(f'Failed to detect critical fields in event: {event}')
                return False

    return True


def detected_keyword(message: str) -> str:
    """
    Parses the string to look for start, stop, or help key words and handles those.
    """
    logger.debug(f'Message: {message}')

    message = message.upper()
    if message.startswith(START_TYPES):
        logger.info('Detected a START_TYPE keyword')
        return START_TEXT
    elif message.startswith(STOP_TYPES):
        logger.info('Detected a STOP_TYPE keyword')
        return STOP_TEXT
    elif message.startswith(HELP_TEXT):
        logger.info('Detected a HELP_TYPE keyword')
        return HELP_TEXT
    else:
        logger.info('No keywords detected...')
        return ''


def set_aws_pinpoint():
    global AWS_PINPOINT
    if AWS_PINPOINT is not None:
        return True
    try:
        AWS_PINPOINT = boto3.client('pinpoint', region_name=AWS_REGION)
        return True
    except Exception as e:
        logger.critical(f'Unable to set pinpoint client: {e}')
        return False


def send_message(recipient_number: str, sender: str, message: str) -> dict:
    try:
        # Should probably be smsv2
        response = AWS_PINPOINT.send_messages(
            ApplicationId=AWS_PINPOINT_APP_ID,
            MessageRequest={
                'Addresses': {
                    recipient_number: {
                        'ChannelType': 'SMS'
                    }
                },
                'MessageConfiguration': {
                    'SMSMessage': {
                        'Body': message,
                        'MessageType': 'TRANSACTIONAL',
                        'OriginationNumber': sender
                    }
                }
            }
        )
        aws_reference = response['MessageResponse']['Result'][recipient_number]['MessageId']
        logging.info(f'Message sent, reference: {aws_reference}')
    except Exception as e:
        logger.exception(e)
        logger.critical(f'Failed to send message: {message} to {recipient_number} from {sender}')


def send_to_service(inbound_sms: dict, url: str) -> None:
    try:
        logger.debug(f'Connecting to {url}, sending: {inbound_sms}')
        response = requests.post(url, data=inbound_sms, timeout=TIMEOUT)
        # If we cannot get the json we want to raise, to push it to SQS
        logger.info(f'Response successful: {response.json()}')
    except Exception as e:
        logger.exception(e)
        logger.error(f'Failed to connect to {url}')
        raise


def push_to_sqs(inbound_sms: dict) -> None:
    try:
        logger.warn(f'Pushing event to SQS')
        logger.debug(f'Event: {inbound_sms}')
        # push to SQS
    except Exception as e:
        logger.critical(f'Failed to push event to SQS: {inbound_sms}')
        push_to_dead_letter(inbound_sms)


def push_to_dead_letter(inbound_sms: dict) -> None:
    pass
