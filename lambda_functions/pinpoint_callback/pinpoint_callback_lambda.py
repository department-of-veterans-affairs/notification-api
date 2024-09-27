import base64
import json
import logging
import os
import uuid

import boto3
from boto3.exceptions.botocore.exceptions import ClientError

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
ROUTING_KEY = 'delivery-status-result-tasks'

# set up logger
logger = logging.getLogger('PinpointCallbackLambda')

try:
    logger.setLevel(LOG_LEVEL)
except ValueError:
    logger.setLevel('INFO')
    logger.warning('Invalid log level specified. Defaulting to INFO.')

# set up sqs resource
try:
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=f"{os.getenv('NOTIFICATION_QUEUE_PREFIX')}{ROUTING_KEY}")
except ClientError as e:
    logger.critical(
        'pinpoint_callback_lambda - ClientError, Failed to create SQS client or could not get sqs queue. '
        'Exception: %s',
        e
    )
    raise
except Exception as e:
    logger.critical(
        'pinpoint_callback_lambda - Unexpected exception, failed to set up SQS client, queue prefix may be missing. '
        'Exception: %s',
        e
    )
    raise


def lambda_handler(
    event,
    context,
):
    for record in event['Records']:
        task = {
            'task': 'process-pinpoint-result',
            'id': str(uuid.uuid4()),
            'args': [{'Message': record['kinesis']['data']}],
            'kwargs': {},
            'retries': 0,
            'eta': None,
            'expires': None,
            'utc': True,
            'callbacks': None,
            'errbacks': None,
            'timelimit': [None, None],
            'taskset': None,
            'chord': None,
        }
        envelope = {
            'body': base64.b64encode(bytes(json.dumps(task), 'utf-8')).decode('utf-8'),
            'content-encoding': 'utf-8',
            'content-type': 'application/json',
            'headers': {},
            'properties': {
                'reply_to': str(uuid.uuid4()),
                'correlation_id': str(uuid.uuid4()),
                'delivery_mode': 2,
                'delivery_info': {'priority': 0, 'exchange': 'default', 'routing_key': ROUTING_KEY},
                'body_encoding': 'base64',
                'delivery_tag': str(uuid.uuid4()),
            },
        }
        msg = base64.b64encode(bytes(json.dumps(envelope), 'utf-8')).decode('utf-8')
        try:
            queue.send_message(MessageBody=msg)
        except ClientError as e:
            logger.critical('pinpoint_callback_lambda - ClientError, Failed to send message to SQS. Exception: %s', e)
            raise

    return {'statusCode': 200}
