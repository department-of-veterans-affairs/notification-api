import base64
from flask import current_app
from app import notify_celery
from typing_extensions import TypedDict
from app.config import QueueNames
import json


class CeleryEvent(TypedDict):
    Message: str


# Create SQS Queue for Process Deliver Status.
@notify_celery.task(bind=True, name="process-delivery-status-result", max_retries=48, default_retry_delay=300)
def process_delivery_status(self, event: CeleryEvent) -> bool:

    # log that we are processing the delivery status
    # current_app.logger.info('processing delivery status: %s', event)

    # required variables to populate
    provider_message = None
    provider_name = None
    provider_level_name = None
    provider_pathname = None
    provider_lineno = None
    provider_time = None
    provider_request_id = None
    provider_application = None
    provider_log_type = None

    # first attempt to process the incoming event
    try:
        sqs_message = json.loads(event['Message'])
    except (json.decoder.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)
        return None

    # next parse the information into variables
    try:
        provider_name = sqs_message.get('provider')
        body = sqs_message.get('body')
        provider = SMSClient.get_provider_client(provider_name)
        notification_platform_status = provider.translate_deliver_status(body)
        provider.should_retry_or_exit()
    except KeyError as e:
        current_app.logger.error("The event stream message data is missing expected attributes.")
        current_app.logger.exception(e)
        current_app.logger.debug(sqs_message)
        self.retry(queue=QueueNames.RETRY)
        return None

    return True

    # GET THE twilio client
    # provider = SMSClient.get_provider_client(message.get('provider'))

    # using twilio client
    # provider.translate_delivery_status()
    # provider.should_retry_or_exit()
    # update_notification()
    # check_and_queue_callback_task(notification)

