import json
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
# import the clients instance from the app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from app import notify_celery, statsd_client, clients, DATETIME_FORMAT
from app.config import QueueNames
from app.dao.service_callback import dao_get_callback_include_payload_status
from app.feature_flags import FeatureFlag, is_feature_enabled

from app.models import (
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    Notification, NOTIFICATION_PREFERENCES_DECLINED
)
FINAL_STATUS_STATES = [NOTIFICATION_DELIVERED, NOTIFICATION_PERMANENT_FAILURE, NOTIFICATION_TECHNICAL_FAILURE,
                       NOTIFICATION_PREFERENCES_DECLINED]


# Create SQS Queue for Process Deliver Status.
@notify_celery.task(bind=True, name="process-delivery-status-result", max_retries=48, default_retry_delay=300)
@statsd(namespace="tasks")
def process_delivery_status(self, event: CeleryEvent):
    """ Celery task for updating the delivery status of a notification """

    if not is_feature_enabled(FeatureFlag.PROCESS_DELIVERY_STATUS_ENABLED):
        current_app.logger.info('Process Delivery Status toggle is disabled.  Skipping callback task.')
        return True

    # log that we are processing the delivery status
    current_app.logger.info('processing delivery status: %s', event)

    # first attempt to process the incoming event
    try:
        sqs_message = json.loads(event['Message'])
    except (json.decoder.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)
        return

    # next parse the information into variables
    try:
        # get the provider
        provider_name = sqs_message.get('provider')
        provider = clients.get_sms_client(provider_name)
        body = sqs_message.get('body')

        # get parameters from notification platform status
        notification_platform_status = provider.translate_delivery_status(body)
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
        return

    current_app.logger.info(
        "Processing Notification Delivery Status. | reference=%s | notification_status=%s | "
        "number_of_message_parts=%s | price_in_millicents_usd=%s",
        reference, notification_status, number_of_message_parts, price_in_millicents_usd
    )

    try:

        # retrieves the inbound message for this provider we are updating the status of the outbound message
        notification, should_retry, should_exit = attempt_to_get_notification(
            reference, notification_status, str(time.time() * 1000)
        )

        # the race condition scenario if we got the delivery status before we actually record the sms
        if should_retry:
            self.retry(queue=QueueNames.RETRY)

        if should_exit:
            return

        assert notification is not None
        ##########################################################################
        # separate method for pricing in the method it would receive the provider
        # if twilio we skip twilio and ignore aws
        ##########################################################################
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

        # statsd - metric tracking of # of messages sent
        statsd_client.incr(f"callback.{provider_name}.{notification_status}")

        if notification.sent_at:
            statsd_client.timing_with_dates(
                'callback.{provider_name}.elapsed-time',
                datetime.datetime.utcnow().strftime(DATETIME_FORMAT),
                notification.sent_at)

        #######################################################################
        # check if payload is to be include in
        # cardinal set in the service callback is (service_id, callback_type)
        #######################################################################
        if dao_get_callback_include_payload_status(notification.service_id, notification.notification_type):
            payload = dict()

        check_and_queue_callback_task(notification, payload)
        return True

    except Retry:
        ###########################################################################################
        # This block exists to preempt executing the "Exception" logic below.  A better approach is
        # to catch specific exceptions where they might occur.
        ###########################################################################################
        raise
    except Exception as e:
        current_app.logger.exception(e)
        self.retry(queue=QueueNames.RETRY)

    return


def attempt_to_get_notification(reference: str, notification_status: str, event_timestamp_in_ms: str) \
        -> Tuple[Notification, bool, bool]:

    should_retry = False
    notification = None

    try:
        notification = dao_get_notification_by_reference(reference)
        should_exit = check_notification_status(notification, notification_status)
    except NoResultFound:
        message_time = datetime.datetime.fromtimestamp(int(event_timestamp_in_ms) / 1000)
        if datetime.datetime.utcnow() - message_time < datetime.timedelta(minutes=5):
            current_app.logger.info(
                'Delivery Status callback event for reference %s was received less than five minutes ago.', reference
            )
            should_retry = True
        else:
            current_app.logger.warning(
                'notification not found for reference: %s (update to %s)', reference, notification_status
            )
        statsd_client.incr('callback.delivery_status.no_notification_found')
        should_exit = True
    except MultipleResultsFound:
        current_app.logger.warning(
            'multiple notifications found for reference: %s (update to %s)', reference, notification_status
        )
        statsd_client.incr('callback.delivery_status.multiple_notifications_found')
        should_exit = True

    return notification, should_retry, should_exit


def log_notification_status_warning(notification, status: str) -> None:
    time_diff = datetime.datetime.utcnow() - (notification.updated_at or notification.created_at)
    current_app.logger.warning(
        'Invalid callback received. Notification id %s received a status update to %s '
        '%s after being set to %s. %s sent by %s',
        notification.id, status, time_diff, notification.status, notification.notification_type, notification.sent_by
    )


def check_notification_status(notification: Notification, notification_status: str) -> bool:
    # Do not update if the status has not changed.
    if notification_status == notification.status:
        current_app.logger.info(
            'SQS callback received the same status of %s for notification %s)',
            notification_status, notification_status
        )
        return True

    # Do not update if notification status is in a final state.
    if notification.status in FINAL_STATUS_STATES:
        log_notification_status_warning(notification, notification_status)
        return True

    return False
