import base64
from flask import current_app
from app import notify_celery
from typing_extensions import TypedDict
from app.config import QueueNames
from app.celery.process_pinpoint_inbound_sms import CeleryEvent
from app.celery.process_pinpoint_receipt_tasks import attempt_to_get_notification
import json
import datetime


# Create SQS Queue for Process Deliver Status.
@notify_celery.task(bind=True, name="process-delivery-status-result", max_retries=48, default_retry_delay=300)
def process_delivery_status(self, event: CeleryEvent):

    # log that we are processing the delivery status
    current_app.logger.info('processing delivery status: %s', event)

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

        if provider_name == 'twilio':
            notification_platform_status = TwilioSMSClient.translate_delivery_status(body)
        else:
            raise Exception("Unknown Provider: %s", provider_name)

        payload = notification_platform_status.get("payload")
        reference = notification_platform_status.get("reference")
        notification_status = notification_platform_status.get("record_status")
        number_of_message_parts = notification_platform_status.get("number_of_message_parts", 0)
        price_in_millicents_usd = notification_platform_status.get("price_in_millicents_usd", 0.0)

    except KeyError as e:
        current_app.logger.error("The event stream message data is missing expected attributes.")
        current_app.logger.exception(e)
        current_app.logger.debug(sqs_message)
        self.retry(queue=QueueNames.RETRY)
        return None

    current_app.logger.info(
        "Processing Notification Delivery Status. | reference=%s | notification_status=%s | "
        "number_of_message_parts=%s | price_in_millicents_usd=%s",
        reference, notification_status, number_of_message_parts, price_in_millicents_usd
    )

    try:
        ###############################################################################
        # retrieves the inbound message for this provider
        # we are updating the status of the outbound message
        ###############################################################################
        notification, should_retry, should_exit = app.celery.process_pinpoint_receipt_tasks.attempt_to_get_notification(
            reference, notification_status, datetime.datetime.now()
        )

        ######################################################################
        # the race condition scenario
        # if we got the delivery status before we actually record the sms
        ######################################################################
        if should_retry:
            self.retry(queue=QueueNames.RETRY)

        if should_exit:
            return

        assert notification is not None
        ###############################################
        # separate method for pricing
        # in the method it would receive the provider
        # if twilio we skip twilio and ignore aws
        ################################################
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
            "Delivery Status callback return status of %s for notification: %s",
            notification_status, notification.id
        )

        # todo: get with kyle / lucas on statsd equivalent twilio
        # statsd - metric tracking of # of messages sent
        statsd_client.incr(f"callback.{provider_name}.{notification_status}")

        if notification.sent_at:
            statsd_client.timing_with_dates(
                'callback.{provider_name}.elapsed-time', datetime.datetime.utcnow(), notification.sent_at)

        # todo: create method for getting the boolean value of "include_provider_payload"
        # this can be found in the notification table

        check_and_queue_callback_task(notification, payload)
        return True

    except Retry:
        # This block exists to preempt executing the "Exception" logic below.  A better approach is
        # to catch specific exceptions where they might occur.
        raise
    except Exception as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)

    return False
