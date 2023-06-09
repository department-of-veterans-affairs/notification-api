from typing import Optional
from sqlalchemy.orm.exc import NoResultFound
from app.va.va_profile.exceptions import VAProfileIdNotFoundException
from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import notify_celery, va_profile_client
from app.config import QueueNames
from app.dao.communication_item_dao import get_communication_item
from app.dao.notifications_dao import get_notification_by_id, update_notification_status_by_id
from app.exceptions import NotificationTechnicalFailureException
from app.models import RecipientIdentifier, NOTIFICATION_PREFERENCES_DECLINED, NOTIFICATION_TECHNICAL_FAILURE
from app.va.va_profile import VAProfileRetryableException
from app.va.va_profile.va_profile_client import CommunicationItemNotFoundException
from app.va.identifier import IdentifierType


@notify_celery.task(
    bind=True, name="lookup-recipient-communication-permissions", max_retries=5, default_retry_delay=300
)
@statsd(namespace="tasks")
def lookup_recipient_communication_permissions(
        self, notification_id: str
) -> None:
    current_app.logger.info(f"Looking up communication preferences for notification_id:{notification_id}")

    notification = get_notification_by_id(notification_id)

    try:
        notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value]
    except (KeyError) as e:
        current_app.logger.info(f'{VAProfileIdNotFoundException.failure_reason} on notification '
                                f'{notification_id}')
        raise VAProfileIdNotFoundException from e

    va_profile_recipient_identifier = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value]

    va_profile_id = va_profile_recipient_identifier.id_value
    communication_item_id = notification.template.communication_item_id
    notification_type = notification.notification_type

    status_reason = recipient_has_given_permission(
        self,
        IdentifierType.VA_PROFILE_ID.value,
        va_profile_id,
        notification_id,
        notification_type,
        communication_item_id
    )

    if status_reason is not None:
        update_notification_status_by_id(notification_id, NOTIFICATION_PREFERENCES_DECLINED,
                                         status_reason=status_reason)
        current_app.logger.info(f"Recipient for notification {notification_id}"
                                f"has declined permission to receive notifications")
        self.request.chain = None


def recipient_has_given_permission(
        task, id_type: str,
        id_value: str,
        notification_id: str,
        notification_type: str,
        communication_item_id: str
) -> Optional[str]:
    default_send_flag = True
    communication_item = None
    identifier = RecipientIdentifier(id_type=id_type, id_value=id_value)

    try:
        communication_item = get_communication_item(communication_item_id)
    except NoResultFound:
        current_app.logger.info('No communication item found for notification %s', notification_id)

    # get default send flag when available
    if communication_item is not None:
        default_send_flag = communication_item.default_send_indicator
    else:
        # Calling va_profile without a communication item won't return anything.
        # Perform default behavior of sending the notification.
        return None

    try:
        is_allowed = va_profile_client.get_is_communication_allowed(
            identifier,
            communication_item.va_profile_item_id if communication_item is not None else None,
            notification_id,
            notification_type
        )
    except VAProfileRetryableException as e:
        current_app.logger.exception(e)
        try:
            task.retry(queue=QueueNames.RETRY)
        except task.MaxRetriesExceededError:
            message = (
                'RETRY FAILED: Max retries reached. '
                f'The task lookup_recipient_communication_permissions failed for notification {notification_id}. '
                'Notification has been updated to technical-failure'
            )

            update_notification_status_by_id(
                notification_id, NOTIFICATION_TECHNICAL_FAILURE, status_reason=e.failure_reason
            )
            raise NotificationTechnicalFailureException(message) from e
    except CommunicationItemNotFoundException:
        current_app.logger.info('Communication item for recipient %s not found on notification %s',
                                id_value, notification_id)

        if default_send_flag:
            return None

        # return status reason message if message should not be sent
        return "No recipient opt-in found for explicit preference"
    else:
        current_app.logger.info('Value of permission for item %s for recipient %s for notification %s: %s',
                                communication_item.va_profile_item_id if communication_item else None,
                                id_value, notification_id, is_allowed)

        if is_allowed:
            return None

        # return status reason message if message should not be sent
        return "Contact preferences set to false"
