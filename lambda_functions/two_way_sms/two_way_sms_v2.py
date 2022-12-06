import boto3
from datetime import datetime
import json
import logging
import os
import psycopg2
import requests
import sys
from functools import lru_cache

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
DATABASE_URI_PATH = ''
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
    global LOG_LEVEL, RETRY_SQS_URL, DATABASE_URI_PATH, TIMEOUT

    try:
        AWS_PINPOINT_APP_ID = os.getenv('AWS_PINPOINT_APP_ID')
        AWS_REGION = 'us-gov-west-1'
        DEAD_LETTER_SQS_URL = os.getenv('DEAD_LETTER_SQS_URL')
        LOG_LEVEL = os.getenv('LOG_LEVEL')
        RETRY_SQS_URL = os.getenv('RETRY_SQS_URL')

        TIMEOUT = os.getenv('TIMEOUT')

        if isinstance(TIMEOUT, list):
            TIMEOUT = tuple(TIMEOUT)
        else:
            TIMEOUT = int(TIMEOUT)

        DATABASE_URI_PATH = os.getenv('DATABASE_URI_PATH')

        if DATABASE_URI_PATH is None:
            # Without this value, this code cannot know the path to the required
            # SSM Parameter Store resource.
            sys.exit("DATABASE_URI_PATH is not set.  Check the Lambda console.")
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
        logger.setLevel(logging.DEBUG)
        # TODO uncomment the below line
        #logger.setLevel(logging.getLevelName(LOG_LEVEL))
    except Exception as e:
        sys.exit('Logger failed to setup properly')


def set_service_two_way_sms_table() -> None:
    """
    Sets the two_way_sms_table_dict if it is not set by opening a connection to the DB and 
    querying the table. This table should be small (a few dozen records at most).
    """
    # format for dict should be: {'number':{'service_id': <value>, 'url_endpoint': <value>, 'self_managed': <value> }}
    logger.info("Beginning retrieval of 10DLC to URL mapping")

    global two_way_sms_table_dict
    try:
        # TODO: remove this assignment.  it is used during testing to bypass data retrieval from the database
        # two_way_sms_table_dict = {
        #    '+16506288615': {
        #        'service_id': 'some_service_id',
        #        'url_endpoint': 'https://eou9ebpdvxw3lva.m.pipedream.net',
        #        'self_managed': True
        #    }
        # }

        logger.info('Connecting to the database . . .')
        logger.info('EMPTY DATABASE URI' if len(SQLALCHEMY_DATABASE_URI) == 0 else SQLALCHEMY_DATABASE_URI[0:5])
        db_connection = psycopg2.connect(SQLALCHEMY_DATABASE_URI)
        logger.info('. . . Connected to the database.')

        data = {}

        with db_connection.cursor() as c:
            logger.info('executing retrieval query')
            # https://www.psycopg.org/docs/cursor.html#cursor.execute
            c.execute(INBOUND_NUMBERS_QUERY)
            data = c.fetchall()
            # TODO change the log statement to debug
            logger.info(f'Data returned from query: {data}')

        db_connection.close()

        two_way_sms_table_dict = {n: {'service_id': s,
                                      'url_endpoint': u,
                                      'self_managed': True if sm == 't' else False} for n, s, u, sm in data}
        logger.info('two_way_sms_table_dict set...')
        logger.debug(f'Two way table as a dictionary with numbers as keys: {two_way_sms_table_dict}')
    except psycopg2.Warning as e:
        logger.warning(e)        
    except psycopg2.Error as e:
        logger.exception(e)
        logger.error(e.pgcode)        
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


def set_database() -> None:
    global SQLALCHEMY_DATABASE_URI

    try:
        logger.info("Getting the database URI from SSM Parameter Store . . .")
        logger.info(DATABASE_URI_PATH)

        # TODO Remove this commented out line.  It is used during debugging to bypass the SSM store from testing
        # SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')

        SQLALCHEMY_DATABASE_URI = read_from_ssm(DATABASE_URI_PATH)

        logger.info("Retrieved DB configuration")
    except Exception as e:
        logger.info(f'Failed to configure database: {e}')
        sys.exit('Unable to configure database')


@lru_cache(maxsize=None)
def read_from_ssm(key: str) -> str:
    try:
        ssm_client = boto3.client('ssm')

        logger.info("Generated ssm_client")

        response = ssm_client.get_parameter(
            Name=key,
            WithDecryption=True
        )

        logger.info("received ssm parameter")

        return response.get("Parameter", {}).get("Value", '')
    except Exception as e:
        logger.error("General Exception With Call to VeText")
        logger.exception(e)
        return ''


def init_execution_environment() -> None:
    """
    Collects environmental variables, sets up the logger, populates the two_way_sms_table_dict,
    and sets up the aws pinpoint and sqs clients.
    """
    set_logger()
    logger.info("Logger configured")
    set_env_variables()
    logger.info("Env vars set")
    set_database()
    logger.info("Database configured")
    set_service_two_way_sms_table()
    logger.info("Services loaded from database")
    set_aws_clients()
    logger.info("Pinpoint and SQS clients configured")

    logger.info('Execution environment setup...')


init_execution_environment()
# ------------------------------------ End Execution Environment Setup ------------------------------------

# ------------------------------------------- Begin Invocation --------------------------------------------


def notify_incoming_sms_handler(event: dict, context: any):
    """
    Handler for inbound messages from SQS.
    """
    logger.info("Context")
    logger.info(context)

    if not valid_event(event):
        logger.critical(f'Logging entire event: {event}')
        # Deadletter
        # we should either push to dead letter queue explicitly or return 500 so that after the specified # of times, the message gets moved to
        #   dead letter. Returning non 200 will re-enqueue the message on to the feeder queue.  Returning 200 removes the item from the queue
        push_to_sqs(event, False)
        # return 500, 'Unrecognized event'
        return create_response(200)

    # SQS events contain 'Records'
    for event_data in event.get('Records'):
        try:
            logger.info('Processing SQS inbound_sms...')

            event_body = event_data.get('body', '')
            event_body = json.loads(event_body)
            logger.info("Retrieved event body")

            inbound_sms = event_body.get('Message', '')
            inbound_sms = json.loads(inbound_sms)
            logger.info("Retrieved message")

            if not valid_event_body(inbound_sms):
                logger.critical(f'Event Body is invalid.  Logging event body: {event_body}')
                push_to_sqs(event_body, False)
                # return 500, 'Unrecognized event'
                return create_response(200)

            # Unsafe lookup intentional to catch missing record
            # destinationNumber is the number the end user responded to (the 10DLC pinpoint number)
            # originationNumber is the veteran number
            two_way_record = two_way_sms_table_dict[inbound_sms.get('destinationNumber')]

            # If the number is not self-managed, look for key words
            if not two_way_record.get('self_managed'):
                logger.info('Service is not self-managed')
                keyword_phrase = detected_keyword(inbound_sms.get('messageBody', ''))
                if keyword_phrase:
                    send_message(two_way_record.get('originationNumber', ''),
                                 two_way_record.get('destinationNumber', ''),
                                 keyword_phrase)

            # Forward inbound_sms to associated service
            logger.info(
                f'Forwarding inbound SMS to service: {two_way_record.get("service_id")} . UrlEndpoint: {two_way_record.get("url_endpoint")}')
            result_of_forwarding = forward_to_service(inbound_sms, two_way_record.get('url_endpoint', ''))

            if not result_of_forwarding:
                logger.info('failed to make request.  Placing request back on retry')
                push_to_sqs(event_body, True)

        except KeyError as e:
            logger.exception(e)
            logger.critical(f'Unable to find two_way_record for: {inbound_sms.get("destinationNumber")}')
            push_to_sqs(event_body, True)
        except Exception as e:
            logger.exception(e)
            # Deadletter
            push_to_sqs(event_body, False)

    return create_response(200)

def create_response(status_code: int = 200):
    response = {
        "statusCode": status_code,
        "isBase64Encoded": False,
        "body": "Success" if status_code == 200 else "Failure"
    }

    return response

def valid_event_body(event_data: dict) -> bool:
    if event_data.get('destinationNumber') is None:
        return False
    if event_data.get('originationNumber') is None:
        return False
    if event_data.get('messageBody') is None:
        return False

    return True


def valid_event(event_data: dict) -> bool:
    """
    Ensure the event has all the necessary fields
    """
    try:
        if 'Records' in event_data:
            for record in event_data.get('Records'):
                if record.get('body') is None:
                    # Log specific record causing issues
                    logger.critical(f'Failed to retrieve body in record: {record}')
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


def forward_to_service(inbound_sms: dict, url: str) -> bool:
    """
    Forwards inbound SMS to the service that has 2-way SMS setup.
    """
    try:
        logger.debug(f'Connecting to {url}, sending: {inbound_sms}')

        headers = {
            'Content-type': 'application/json'
        }

        response = requests.post(
            url,            
            verify=False,
            json=inbound_sms,
            timeout=TIMEOUT,
            headers=headers
        )

        # If we cannot get the json, raise and push it to SQS
        logger.info(f'Response Status: {response.status_code}')
        logger.debug(f"Response Content: {response.content}")

        return True
    except requests.HTTPError as e:
        logger.error("HTTPError With Http Request")
        logger.exception(e)
    except requests.RequestException as e:
        logger.error("RequestException With Http Request")
        logger.exception(e)
    except Exception as e:
        logger.error("General Exception With Http Request")
        logger.exception(e)
        # Need to raise here to move the message to the dead letter queue instead of retry. 
        raise

    return False


def push_to_sqs(inbound_sms: dict, is_retry: bool) -> None:
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

        aws_sqs_client.send_message(QueueUrl=RETRY_SQS_URL if is_retry else DEAD_LETTER_SQS_URL,
                                    MessageBody=queue_msg)

        logger.info('Completed enqueue of message')
    except Exception as e:
        logger.exception(e)
        logger.critical(f'Failed to push event to SQS: {inbound_sms}')
        if is_retry:
            push_to_sqs(inbound_sms, False)
        else:
            logger.critical(f'Attempt to enqueue to DEAD LETTER failed')
