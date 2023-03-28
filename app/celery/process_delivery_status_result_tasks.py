import math
import time
import datetime
from app.celery.service_callback_tasks import check_and_queue_callback_task
from app.celery.process_pinpoint_inbound_sms import CeleryEvent

from app.dao.notifications_dao import (
    dao_get_notification_by_reference,
    dao_update_notification,
    update_notification_status_by_id,
)

from typing import Tuple
from celery.exceptions import Retry
from flask import current_app

from notifications_utils.statsd_decorators import statsd
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from app import notify_celery, statsd_client, clients, DATETIME_FORMAT
from app.config import QueueNames
from app.dao.service_callback_dao import dao_get_callback_include_payload_status

from app.models import (
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    Notification,
    NOTIFICATION_PREFERENCES_DECLINED,
)

FINAL_STATUS_STATES = [
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_PREFERENCES_DECLINED,
]


# Create SQS Queue for Process Deliver Status.
@notify_celery.task(bind=True, name="process-delivery-status-result", max_retries=48, default_retry_delay=300, )
@statsd(namespace="tasks")
def process_delivery_status(self, event: CeleryEvent) -> bool:

    """Celery task for updating the delivery status of a notification"""

    # preset variables to address "unbounded local variable"
    sqs_message = None
    notification_platform_status = None

    # log that we are processing the delivery status
    current_app.logger.info("processing delivery status: %s", event)

    # first attempt to process the incoming event
    sqs_message = _get_sqs_message(self, event)

    # get the provider
    (provider_name, provider) = _get_provider_info(self, sqs_message)

    body = sqs_message.get("body")
    current_app.logger.info("retrieved delivery status body: %s", body)

    # get notification_platform_status
    notification_platform_status = _get_notification_platform_status(self, provider, body, sqs_message)

    # get parameters from notification platform status
    (payload, reference, notification_status,
     number_of_message_parts, price_in_millicents_usd) = _get_notification_parameters(notification_platform_status)

    # retrieves the inbound message for this provider we are updating the status of the outbound message
    notification, should_retry, should_exit = attempt_to_get_notification(
        reference, notification_status, str(time.time() * 1000)
    )

    # the race condition scenario if we got the delivery status before we actually record the sms
    if should_retry or (notification is None):
        self.retry(queue=QueueNames.RETRY)

    if should_exit:
        return False

    try:
        # calculate pricing
        _calculate_pricing(price_in_millicents_usd, notification, notification_status, number_of_message_parts)
        current_app.logger.info(
            "Delivery Status callback return status of %s for notification: %s",
            notification_status,
            notification.id,
        )

        # statsd - metric tracking of # of messages sent
        _increment_statsd(notification, provider_name, notification_status)

        # check if payload is to be include in cardinal set in the service callback is (service_id, callback_type)
        if not _get_include_payload_status(self, notification):
            payload = {}
        check_and_queue_callback_task(notification, payload)
        return True

    except Retry:
        # This block exists to preempt executing the "Exception" logic below.  A better approach is
        # to catch specific exceptions where they might occur.
        raise
    except Exception as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)

    return True


def attempt_to_get_notification(
        reference: str, notification_status: str, event_timestamp_in_ms: str
) -> Tuple[Notification, bool, bool]:
    """ Attempt to get the notification object and determine whether the Celery Event should be retry or exit"""
    should_retry = False
    notification = None
    try:
        notification = dao_get_notification_by_reference(reference)
        should_exit = check_notification_status(notification, notification_status)
    except NoResultFound:
        message_time = datetime.datetime.fromtimestamp(
            math.floor(float(event_timestamp_in_ms) / 1000)
        )
        if datetime.datetime.utcnow() - message_time < datetime.timedelta(minutes=5):
            current_app.logger.info(
                "Delivery Status callback event for reference %s was received less than five minutes ago.",
                reference,
            )
            should_retry = True
        else:
            current_app.logger.warning(
                "notification not found for reference: %s (update to %s)",
                reference,
                notification_status,
            )
        statsd_client.incr("callback.delivery_status.no_notification_found")
        should_exit = True
    except MultipleResultsFound:
        current_app.logger.warning(
            "multiple notifications found for reference: %s (update to %s)",
            reference,
            notification_status,
        )
        statsd_client.incr("callback.delivery_status.multiple_notifications_found")
        should_exit = True

    return notification, should_retry, should_exit


def log_notification_status_warning(notification, status: str) -> None:
    time_diff = datetime.datetime.utcnow() - (notification.updated_at or notification.created_at)
    current_app.logger.warning(
        "Invalid callback received. Notification id %s received a status update to %s "
        "%s after being set to %s. %s sent by %s",
        notification.id,
        status,
        time_diff,
        notification.status,
        notification.notification_type,
        notification.sent_by,
    )


def check_notification_status(notification: Notification, notification_status: str) -> bool:
    # Do not update if the status has not changed.
    if notification_status == notification.status:
        current_app.logger.info(
            "SQS callback received the same status of %s for notification %s)",
            notification_status,
            notification_status,
        )
        return True

    # Do not update if notification status is in a final state.
    if notification.status in FINAL_STATUS_STATES:
        log_notification_status_warning(notification, notification_status)
        return True

    return False


def _get_notification_parameters(notification_platform_status):
    """ Get the payload, notification reference, notification status, etc from the notification_platform_status """
    payload = notification_platform_status.get("payload")
    reference = notification_platform_status.get("reference")
    notification_status = notification_platform_status.get("record_status")
    number_of_message_parts = notification_platform_status.get("number_of_message_parts", 1)
    price_in_millicents_usd = notification_platform_status.get("price_in_millicents_usd", 0.0)
    current_app.logger.info(
        "Processing Notification Delivery Status. | reference=%s | notification_status=%s | "
        "number_of_message_parts=%s | price_in_millicents_usd=%s",
        reference,
        notification_status,
        number_of_message_parts,
        price_in_millicents_usd,
    )
    return payload, reference, notification_status, number_of_message_parts, price_in_millicents_usd


def _calculate_pricing(price_in_millicents_usd, notification, notification_status, number_of_message_parts):
    """ Calculate pricing """
    if price_in_millicents_usd > 0.0:
        notification.status = notification_status
        notification.segments_count = number_of_message_parts
        notification.cost_in_millicents = price_in_millicents_usd
        dao_update_notification(notification)
    else:
        # notification_id -  is the UID in the database for the notification
        # status - is the notification platform status generated earlier
        update_notification_status_by_id(
            notification_id=notification.id, status=notification_status
        )


def _get_notification_platform_status(self, provider, body, sqs_message):
    """ Performs a translation on the body """
    notification_platform_status = None
    try:
        notification_platform_status = provider.translate_delivery_status(body)
    except (ValueError, KeyError) as e:
        current_app.logger.error("The event stream body could not be translated.")
        current_app.logger.exception(e)
        current_app.logger.debug(sqs_message)
        self.retry(queue=QueueNames.RETRY)

    current_app.logger.info(
        "retrieved delivery status: %s", notification_platform_status
    )

    # notification_platform_status cannot be None
    if notification_platform_status is None:
        current_app.logger.error("Notification Platform Status cannot be None")
        current_app.logger.debug(body)
        self.retry(queue=QueueNames.RETRY)

    return notification_platform_status


def _get_include_payload_status(self, notification):
    """ Determines where payload should be included in delivery status callback data"""
    include_payload_status = False

    try:
        include_payload_status = dao_get_callback_include_payload_status(
            notification.service_id,
            notification.notification_type
        )

    except NoResultFound:
        # It is acceptable for this exception to happen but we want to log it
        current_app.logger.info("ServiceCallback include_payload for notification is unavailable or false")
        current_app.logger.debug(notification)

    except (AttributeError, TypeError) as e:
        current_app.logger.error("Could not determine include_payload property for ServiceCallback.")
        current_app.logger.exception(e)
        current_app.logger.debug(notification)
        self.retry(queue=QueueNames.RETRY)

    return include_payload_status


def _increment_statsd(notification, provider_name, notification_status):
    statsd_client.incr(f"callback.{provider_name}.{notification_status}")

    if notification.sent_at:
        statsd_client.timing_with_dates(
            f"callback.{provider_name}.elapsed-time",
            datetime.datetime.utcnow().strftime(DATETIME_FORMAT),
            notification.sent_at,
        )


def _get_sqs_message(self, event):
    """ Gets the sms message from the CeleryEvent """
    sqs_message = None
    try:
        sqs_message = event["message"]
    except (TypeError, KeyError) as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)

    return sqs_message


def _get_provider_info(self, sqs_message):
    """ Gets the provider_name and provider object """
    provider_name = sqs_message.get("provider")
    provider = clients.get_sms_client(provider_name)

    # provider cannot None
    if provider is None:
        current_app.logger.error("Provider cannot be None")
        current_app.logger.debug(sqs_message)
        self.retry(queue=QueueNames.RETRY)

    return provider_name, provider
