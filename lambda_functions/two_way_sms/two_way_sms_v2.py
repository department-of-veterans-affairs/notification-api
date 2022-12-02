import boto3
from datetime import datetime
import json
import logging
from os import sys, environ
import psycopg2
import requests


# Global Variables
# Constants
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

# Pre-defined env variables
AWS_PINPOINT_APP_ID = ''
AWS_REGION = ''
DEAD_LETTER_SQS_URL = ''
LOG_LEVEL = 'INFO'
RETRY_SQS_URL = ''
SQLALCHEMY_DATABASE_URI = ''
TIMEOUT = 3

# Set within lambda
logger = None
aws_pinpoint_client = None
aws_sqs_client = None
two_way_sms_table_dict = {}


def set_env_variables() -> None:
    """
    Attempt to get environmental variables. Abort execution environment on failure.
    """
    global AWS_PINPOINT_APP_ID, AWS_REGION, DEAD_LETTER_SQS_URL
    global LOG_LEVEL, RETRY_SQS_URL, SQLALCHEMY_DATABASE_URI, TIMEOUT

    try:
        AWS_PINPOINT_APP_ID = environ['aws_pinpoint_app_id']
        AWS_REGION = environ['aws_region']
        DEAD_LETTER_SQS_URL = environ['dead_letter_sqs_url']
        LOG_LEVEL = environ['log_level']
        RETRY_SQS_URL = environ['retry_sqs_url']
        SQLALCHEMY_DATABASE_URI = environ['sql_alchemy_database_uri']
        TIMEOUT = environ['timeout']
        if isinstance(TIMEOUT, list):
            TIMEOUT = tuple(TIMEOUT)
        else:
            TIMEOUT = int(TIMEOUT)
    except KeyError as e:
        sys.exit(f'Failed to find env variable: {e}')
    except Exception as e:
        sys.exit(f'Failed to convert TIMEOUT: {e}')


def set_logger() -> None:
    """
    Sets custom logger for the lambda.
    """
    global logger
    try:
        logger = logging.getLogger('TwoWaySMSv2')
        logger.setLevel(logging.getLevelName(LOG_LEVEL))
    except Exception as e:
        sys.exit('Logger failed to setup properly')


def make_database_connection() -> psycopg2.connection:
    """
    Return a connection to the database, or return None.

    https://www.psycopg.org/docs/module.html#psycopg2.connect
    https://www.psycopg.org/docs/module.html#exceptions
    """
    try:
        logger.debug('Connecting to the database . . .')
        connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI)
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
    Sets the two_way_sms_table_dict if it is not set by opening a connection to the DB and 
    querying the table. This table should be small (a few dozen records at most).
    """
    # format for dict should be: {'number':{'service_id': <value>, 'url_endpoint': <value>, 'self_managed': <value> }}
    global two_way_sms_table_dict
    try:
        db_connection = make_database_connection()
        data = {}
        with db_connection.cursor() as c:
            # https://www.psycopg.org/docs/cursor.html#cursor.execute
            c.execute(INBOUND_NUMBERS_QUERY)
            data = c.fetchall()
            logger.debug(f'Data returned from query: {data}')
        db_connection.close()

        two_way_sms_table_dict = {n: {'service_id': s,
                                      'url_endpoint': u,
                                      'self_managed': True if sm == 't' else False} for n, s, u, sm in data}
        logger.info('two_way_sms_table_dict set...')
        logger.debug(f'Two way table as a dictionary with numbers as keys: {two_way_sms_table_dict}')
    except Exception as e:
        logger.critical(f'Failed to query database: {e}')
        if db_connection:
            db_connection.close()
        sys.exit('Unable to load inbound_numbers table into dictionary')


def set_aws_clients():
    global aws_pinpoint_client, aws_sqs_client
    if aws_pinpoint_client is not None and aws_sqs_client is not None:
        return True
    try:
        logger.info('Setting aws_pinpoint_client...')
        aws_pinpoint_client = boto3.client('pinpoint', region_name=AWS_REGION)
        logger.info('aws_pinpoint_client set...')

        logger.info('Setting aws_sqs_client...')
        aws_sqs_client = boto3.client('sqs', region_name=AWS_REGION)
        logger.info('aws_sqs_client set...')

        return True
    except Exception as e:
        logger.critical(f'Unable to set pinpoint client: {e}')
        return False


def init_execution_environment() -> None:
    """
    Collects environmental variables, sets up the logger, populates the two_way_sms_table_dict,
    and sets up the aws pinpoint and sqs clients.
    """
    set_env_variables()
    set_logger()
    set_service_two_way_sms_table()
    set_aws_clients()
    logger.info('Execution environment setup...')


init_execution_environment()
# ------------------------------------ End Execution Environment Setup ------------------------------------

# ------------------------------------------- Begin Invocation --------------------------------------------


def two_way_sms_v2_handler(event: dict, context):
    """
    Handler for inbound messages from SNS.
    """
    if not valid_event(event):
        logger.critical(f'Logging entire event: {event}')
        # Deadletter
        push_to_sqs(event, False)
        return 500, 'Unrecognized event'

    # Both SNS and SQS seem to contain 'Records', will confirm.
    for event_data in event.get('Records'):
        try:
            inbound_sms = event_data.get('Sns')
            # This is where it gets fuzzy. I have seen multiple versions of what is in the SNS. Need to test.
            # Will derive logic for sns vs sqs messages when I can test them
            is_sns = 'dateReceived' not in inbound_sms

            # Update and log SNS or SQS inbound_sms
            if is_sns:
                logger.info('Processing SNS inbound_sms...')
                inbound_sms['dateReceived'] = datetime.utcnow()
            else:
                logger.info('Processing SQS inbound_sms...')

            # Unsafe lookup intentional to catch missing record
            two_way_record = two_way_sms_table_dict[inbound_sms.get('originationNumber')]

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
            forward_to_service(inbound_sms)
        except KeyError as e:
            logger.exception(e)
            logger.critical(f'Unable to find two_way_record for: {inbound_sms.get("originationNumber")}')
            push_to_sqs(inbound_sms, True, is_sns)
        except Exception as e:
            logger.exception(e)
            # Deadletter
            push_to_sqs(inbound_sms, False, is_sns)
    return 200, 'Success'


def valid_event(event_data: dict) -> bool:
    """
    Ensure the event has all the necessary fields
    """
    try:
        if 'Records' in event_data:
            for record in event_data.get('Records'):
                inbound_sms = record.get('Sns')
                if not inbound_sms or not EXPECTED_SNS_FIELDS.issubset(inbound_sms):
                    # Log specific record causing issues
                    logger.critical(f'Failed to detect critical fields in record: {record}')
                    return False
        return True
    except Exception as e:
        logger.critical(f'Failed to parse event_data')
        return False


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


def send_message(recipient_number: str, sender: str, message: str) -> dict:
    """
    Called when we are monitoring for keywords and one was detected. This sends the 
    appropriate response to the phone number that requested a message via keyword.
    """
    try:
        # Should probably be smsv2
        response = aws_pinpoint_client.send_messages(
            ApplicationId=AWS_PINPOINT_APP_ID,
            MessageRequest={'Addresses': {recipient_number: {'ChannelType': 'SMS'}},
                            'MessageConfiguration': {'SMSMessage': {'Body': message,
                                                                    'MessageType': 'TRANSACTIONAL',
                                                                    'OriginationNumber': sender}}}
        )
        aws_reference = response['MessageResponse']['Result'][recipient_number]['MessageId']
        logging.info(f'Message sent, reference: {aws_reference}')
    except Exception as e:
        logger.exception(e)
        logger.critical(f'Failed to send message: {message} to {recipient_number} from {sender}')


def forward_to_service(inbound_sms: dict, url: str) -> None:
    """
    Forwards inbound SMS to the service that has 2-way SMS setup.
    """
    try:
        logger.debug(f'Connecting to {url}, sending: {inbound_sms}')
        response = requests.post(url, data=inbound_sms, timeout=TIMEOUT)
        # If we cannot get the json, raise and push it to SQS
        logger.info(f'Response successful: {response.json()}')
    except Exception as e:
        logger.exception(e)
        logger.error(f'Failed to connect to {url}')
        raise


def push_to_sqs(inbound_sms: dict, is_retry: bool, is_sns: bool = 'unknown') -> None:
    """
    Pushes an inbound sms or entire event to SQS. Sends to RETRY or DEAD LETTER queue dependent
    on is_retry variable. Also identifies the source (sns, sqs, or unknown).
    """
    # NOTE: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SendMessage.html
    # Need to ensure none of those unicode characters are in the message or it's gone
    try:
        logger.warning(f'Pushing event to {"RETRY" if is_retry else "DEAD LETTER"} queue')
        logger.debug(f'Event: {inbound_sms}')

        queue_msg = json.dumps(inbound_sms)
        queue_msg_attrs = {'source': {'DataType': 'String',
                                      'StringValue': is_sns}}

        aws_sqs_client.send_message(QueueUrl=RETRY_SQS_URL if is_retry else DEAD_LETTER_SQS_URL,
                                    MessageAttributes=queue_msg_attrs,
                                    MessageBody=queue_msg)

        logger.info('Completed enqueue of message')
    except Exception as e:
        logger.exception(e)
        logger.critical(f'Failed to push event to SQS: {inbound_sms}')
        if is_retry:
            push_to_sqs(inbound_sms, False, is_sns)
        else:
            logger.critical(f'Attempt to enqueue to DEAD LETTER failed')
