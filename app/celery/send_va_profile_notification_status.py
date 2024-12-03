from flask import current_app
import requests

from app import notify_celery, va_profile_client
from app.celery.exceptions import AutoRetryException
from app.constants import (
    DATETIME_FORMAT,
    EMAIL_TYPE,
)
from app.feature_flags import FeatureFlag, is_feature_enabled
from app.models import Notification


def check_and_queue_va_profile_email_status_callback(notification: Notification) -> None:
    """
    This checks the feature flag is enabled. If it is, queues the celery task and collects data from the notification.
    Otherwise, it only logs a message.

    :param notification: the email notification to collect data from
    """
    current_app.logger.debug(
        'Sending email status to VA Profile, checking feature flag... | notification %s', notification.id
    )

    if is_feature_enabled(FeatureFlag.VA_PROFILE_SMS_STATUS_ENABLED) or notification.notification_type == EMAIL_TYPE:
        current_app.logger.debug(
            'Sending email status to VA Profile, collecting data for notification %s', notification.id
        )
        notification_data = {
            'id': str(notification.id),  # this is the notification id
            'reference': notification.client_reference,
            'to': notification.to,  # this is the recipient's contact info (email)
            'status': notification.status,  # this will specify the delivery status of the notification
            'status_reason': notification.status_reason,  # populated if there's additional context on the delivery status
            'created_at': notification.created_at.strftime(DATETIME_FORMAT),  # noqa: F821
            'completed_at': notification.updated_at.strftime(DATETIME_FORMAT) if notification.updated_at else None,
            'sent_at': notification.sent_at.strftime(DATETIME_FORMAT) if notification.sent_at else None,
            'notification_type': notification.notification_type,  # this is the channel/type of notification (email)
            'provider': notification.sent_by,  # email provider
        }

        # data passed to tasks must be JSON serializable
        send_email_status_to_va_profile.delay(notification_data)
    else:
        current_app.logger.debug(
            'SMS status not sent to VA Profile, feature flag disabled | notification %s', notification.id
        )


@notify_celery.task(
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=60,
    retry_backoff=True,
    retry_backoff_max=3600,
)
def send_email_status_to_va_profile(notification_data: dict) -> None:
    """
    This function calls the VAProfileClient method to send the information to VA Profile.

    :param notification_data: the email notification data to send
    """

    try:
        va_profile_client.send_va_profile_email_status(notification_data)
    except requests.Timeout:
        # logging in send_va_profile_email_status
        raise AutoRetryException
    except requests.RequestException:
        # logging in send_va_profile_email_status
        # In this case the error is being handled by not retrying this celery task
        pass
