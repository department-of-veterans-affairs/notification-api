from app import notify_celery
from app.celery.common import (
    can_retry,
    handle_max_retries_exceeded,
    log_and_update_permanent_failure,
    log_and_update_critical_failure,
)
from app.celery.exceptions import NonRetryableException, AutoRetryException
from app.celery.service_callback_tasks import check_and_queue_callback_task
from app.clients.email.aws_ses import AwsSesClientThrottlingSendRateException
from app.config import QueueNames
from app.constants import (
    STATUS_REASON_BLOCKED,
    STATUS_REASON_INVALID_NUMBER,
    STATUS_REASON_UNDELIVERABLE,
    STATUS_REASON_UNREACHABLE,
)
from app.dao import notifications_dao
from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_service_id_and_number
from app.delivery import send_to_providers
from app.exceptions import (
    InactiveServiceException,
    InvalidProviderException,
    NotificationTechnicalFailureException,
)
from app.models import Notification
from app.v2.errors import RateLimitError

from celery import Task
from flask import current_app
from notifications_utils.field import NullValueForNonConditionalPlaceholderException
from notifications_utils.recipients import InvalidEmailError, InvalidPhoneError
from notifications_utils.statsd_decorators import statsd


# Including sms_sender_id is necessary in case it's passed in when being called
@notify_celery.task(
    bind=True,
    name='deliver_sms',
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=True,
    retry_backoff_max=60,
)
@statsd(namespace='tasks')
def deliver_sms(
    task: Task,
    notification_id,
    sms_sender_id=None,
):
    current_app.logger.info('Start sending SMS for notification id: %s', notification_id)

    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            # Distributed computing race condition
            current_app.logger.warning('Notification not found for: %s, retrying', notification_id)
            raise AutoRetryException
        if not notification.to:
            raise RuntimeError(
                f'The "to" field was not set for notification {notification_id}.  This is a programming error.'
            )
        send_to_providers.send_sms_to_provider(notification, sms_sender_id)
        current_app.logger.info('Successfully sent sms for notification id: %s', notification_id)
    except Exception as e:
        _handle_delivery_failure(task, notification, 'deliver_sms', e)


# Including sms_sender_id is necessary in case it's passed in when being called
@notify_celery.task(
    bind=True,
    name='deliver_sms_with_rate_limiting',
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=2,
    retry_backoff_max=60,
)
@statsd(namespace='tasks')
def deliver_sms_with_rate_limiting(
    task: Task,
    notification_id,
    sms_sender_id=None,
):
    from app.notifications.validators import check_sms_sender_over_rate_limit

    current_app.logger.info('Start sending SMS with rate limiting for notification id: %s', notification_id)

    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            current_app.logger.warning('Notification not found for: %s, retrying', notification_id)
            raise AutoRetryException
        if not notification.to:
            raise RuntimeError(
                f'The "to" field was not set for notification {notification_id}.  This is a programming error.'
            )
        sms_sender = dao_get_service_sms_sender_by_service_id_and_number(
            notification.service_id, notification.reply_to_text
        )
        check_sms_sender_over_rate_limit(notification.service_id, sms_sender)
        send_to_providers.send_sms_to_provider(notification, sms_sender_id)
        current_app.logger.info('Successfully sent sms with rate limiting for notification id: %s', notification_id)
    except RateLimitError:
        retry_time = sms_sender.rate_limit_interval / sms_sender.rate_limit
        current_app.logger.info(
            'SMS notification delivery for id: %s failed due to rate limit being exceeded. '
            'Will retry in %s seconds.',
            notification_id,
            retry_time,
        )

        task.retry(queue=QueueNames.RETRY, max_retries=None, countdown=retry_time)
    except Exception as e:
        _handle_delivery_failure(task, notification, 'deliver_sms_with_rate_limiting', e)


# Including sms_sender_id is necessary in case it's passed in when being called.
@notify_celery.task(
    bind=True,
    name='deliver_email',
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=True,
    retry_backoff_max=60,
)
@statsd(namespace='tasks')
def deliver_email(
    task: Task,
    notification_id: str,
    sms_sender_id=None,
):
    current_app.logger.info('Start sending email for notification id: %s', notification_id)

    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            current_app.logger.warning('Notification not found for: %s, retrying', notification_id)
            raise AutoRetryException
        if not notification.to:
            raise RuntimeError(
                f'The "to" field was not set for notification {notification_id}.  This is a programming error.'
            )
        send_to_providers.send_email_to_provider(notification)
        current_app.logger.info('Successfully sent email for notification id: %s', notification_id)
    except AwsSesClientThrottlingSendRateException as e:
        current_app.logger.warning(
            'RETRY number %s: Email notification %s was rate limited by SES',
            task.request.retries,
            notification_id,
        )
        raise AutoRetryException(f'Found {type(e).__name__}, autoretrying...', e, e.args)

    except Exception as e:
        _handle_delivery_failure(task, notification, 'deliver_email', e)


def _handle_delivery_failure(
    celery_task: Task,
    notification: Notification,
    method_name: str,
    e: Exception,
) -> None:
    """Handle the various exceptions that can be raised during the delivery of an email or SMS notification

    Args:
        celery_task (Task): The task that raised an exception
        notification (Notification): The notification that failed to send
        method_name (str): The name of the method that raised an exception
        e (Exception): The exception that was raised

    Raises:
        NotificationTechnicalFailureException: If the exception is a technical failure
        AutoRetryException: If the exception can be retried
    """
    if isinstance(e, (InactiveServiceException, InvalidProviderException)):
        log_and_update_critical_failure(
            notification.id,
            method_name,
            e,
            STATUS_REASON_UNDELIVERABLE,
        )
        raise NotificationTechnicalFailureException from e

    elif isinstance(e, InvalidPhoneError):
        log_and_update_permanent_failure(
            notification.id,
            method_name,
            e,
            STATUS_REASON_INVALID_NUMBER,
        )
        raise NotificationTechnicalFailureException from e

    elif isinstance(e, InvalidEmailError):
        log_and_update_permanent_failure(
            notification.id,
            method_name,
            e,
            STATUS_REASON_UNREACHABLE,
        )
        raise NotificationTechnicalFailureException from e

    elif isinstance(e, NonRetryableException):
        if 'opted out' in str(e).lower():
            status_reason = STATUS_REASON_BLOCKED
        else:
            # Calling out this includes that are too long.
            status_reason = STATUS_REASON_UNDELIVERABLE

        log_and_update_permanent_failure(
            notification.id,
            method_name,
            e,
            status_reason,
        )
        # Expected chain termination
        celery_task.request.chain = None

    elif isinstance(e, (NullValueForNonConditionalPlaceholderException, AttributeError, RuntimeError)):
        log_and_update_critical_failure(
            notification.id,
            method_name,
            e,
            STATUS_REASON_UNDELIVERABLE,
        )
        raise NotificationTechnicalFailureException(f'Found {type(e).__name__}, NOT retrying...', e, e.args)

    else:
        current_app.logger.exception(
            '%s delivery failed for notification %s', notification.notification_type, notification.id
        )

        if can_retry(celery_task.request.retries, celery_task.max_retries, notification.id):
            current_app.logger.warning(
                '%s unable to send for notification %s, retrying',
                notification.notification_type,
                notification.id,
            )
            raise AutoRetryException(f'Found {type(e).__name__}, autoretrying...', e, e.args)

        else:
            msg = handle_max_retries_exceeded(notification.id, method_name)
            check_and_queue_callback_task(notification)
            raise NotificationTechnicalFailureException(msg)
