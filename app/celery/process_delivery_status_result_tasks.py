import base64
from flask import current_app
from app import notify_celery
from typing_extensions import TypedDict
from app.config import QueueNames
from app.celery.process_pinpoint_inbound_sms import CeleryEvent
from app.celery.process_pinpoint_receipt_tasks import attempt_to_get_notification
import json


# Create SQS Queue for Process Deliver Status.
@notify_celery.task(bind=True, name="process-delivery-status-result", max_retries=48, default_retry_delay=300)
def process_delivery_status(self, event: CeleryEvent) -> bool:

    # log that we are processing the delivery status
    current_app.logger.info('processing delivery status: %s', event)

    # first attempt to process the incoming event
    try:
        sqs_message = json.loads(event['Message'])
    except (json.decoder.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)
        return False

    # next parse the information into variables
    try:
        provider_name = sqs_message.get('provider')
        body = sqs_message.get('body')
        if provider_name == 'twilio':
            notification_platform_status = TwilioSMSClient.translate_delivery_status(body)
        else:
            raise Exception('Unknown provider: %s', provider_name)

    except KeyError as e:
        current_app.logger.error("The event stream message data is missing expected attributes.")
        current_app.logger.exception(e)
        current_app.logger.debug(sqs_message)
        self.retry(queue=QueueNames.RETRY)
        return False

    try:
        ###############################################################################
        # retrieves the inbound message for this provider
        # we are updating the status of the outbound message
        ###############################################################################
        notification, should_retry, should_exit = attempt_to_get_notification(
            notification_platform_status.reference,
            notification_platform_status.record_status,
            # notification_platform_status.event_timestamp
            datetime.datetime.utcnow()
            # python get current date pinpoint_message['event_timestamp']
        )
        ######################################################################
        # the race condition scenario
        # if we got the delivery status before we actually record the sms
        ######################################################################
        if should_retry:
            self.retry(queue=QueueNames.RETRY)

        if should_exit:
            return False

        assert notification is not None

        if price_in_millicents_usd > 0.0:
            notification.status = notification_status
            notification.segments_count = number_of_message_parts
            notification.cost_in_millicents = price_in_millicents_usd
            dao_update_notification(notification)
        else:
            ######################################################################
            # notification_id -  is the UID in the database for the notification
            # status - is the notification platform status generated earlier
            ######################################################################
            update_notification_status_by_id(
                notification_id=notification.id,
                status=notification_status
            )

        current_app.logger.info(
            "SQS Delivery callback return status of %s for notification: %s",
            notification_status, notification.id
        )

        # todo: get with kyle / lucas on statsd equivalent twilio
        # statsd - metric tracking of # of messages sent
        statsd_client.incr(f"callback.[sqs_delivery_name].{notification_status}")

        if notification.sent_at:
            statsd_client.timing_with_dates(
                'callback.[sqs_delivery_name].elapsed-time', datetime.datetime.utcnow(), notification.sent_at)

        check_and_queue_callback_task(notification)

        return True

    except Retry:
        # This block exists to preempt executing the "Exception" logic below.  A better approach is
        # to catch specific exceptions where they might occur.
        raise
    except Exception as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)

    return False

    # GET THE twilio client
    # provider = SMSClient.get_provider_client(message.get('provider'))

    # using twilio client
    # provider.translate_delivery_status()
    # provider.should_retry_or_exit()
    # update_notification()
    # check_and_queue_callback_task(notification)

