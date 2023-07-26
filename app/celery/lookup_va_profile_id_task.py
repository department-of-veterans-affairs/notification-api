from app.exceptions import NotificationTechnicalFailureException, NotificationPermanentFailureException
from app.models import RecipientIdentifier, NOTIFICATION_TECHNICAL_FAILURE, \
    NOTIFICATION_PERMANENT_FAILURE
from flask import current_app
from notifications_utils.statsd_decorators import statsd
from app import notify_celery
from app.celery.common import can_retry, handle_max_retries_exceeded
from app.celery.exceptions import AutoRetryException
from app.dao import notifications_dao
from app import mpi_client
from app.va.identifier import IdentifierType, UnsupportedIdentifierException
from app.va.mpi import MpiRetryableException, BeneficiaryDeceasedException, \
    IdentifierNotFound, MultipleActiveVaProfileIdsException, IncorrectNumberOfIdentifiersException, \
    NoSuchIdentifierException
from app.celery.service_callback_tasks import check_and_queue_callback_task


@notify_celery.task(bind=True, name="lookup-va-profile-id-tasks",
                    throws=(AutoRetryException, ),
                    autoretry_for=(AutoRetryException, ),
                    max_retries=2886, retry_backoff=True, retry_backoff_max=60)
@statsd(namespace="tasks")
def lookup_va_profile_id(self, notification_id):
    current_app.logger.info(f"Retrieving VA Profile ID from MPI for notification {notification_id}")
    notification = notifications_dao.get_notification_by_id(notification_id)

    try:
        va_profile_id = mpi_client.get_va_profile_id(notification)
        notification.recipient_identifiers.set(
            RecipientIdentifier(
                notification_id=notification.id,
                id_type=IdentifierType.VA_PROFILE_ID.value,
                id_value=va_profile_id
            ))
        notifications_dao.dao_update_notification(notification)
        current_app.logger.info(
            f"Successfully updated notification {notification_id} with VA PROFILE ID {va_profile_id}"
        )

        return va_profile_id

    except MpiRetryableException as e:
        if can_retry(self.request.retries, self.max_retries, notification_id, current_app.logger):
            current_app.logger.warning("Unable to lookup VA Profile ID for notification id: %s, retrying",
                                       notification_id)
            raise AutoRetryException('Found MpiRetryableException, autoretrying...', e, e.args)
        else:
            msg = handle_max_retries_exceeded(notification_id, 'lookup_va_profile_id', current_app.logger)
            raise NotificationTechnicalFailureException(msg)

    except (BeneficiaryDeceasedException, IdentifierNotFound, MultipleActiveVaProfileIdsException,
            UnsupportedIdentifierException, IncorrectNumberOfIdentifiersException, NoSuchIdentifierException) as e:
        message = f"{e.__class__.__name__} - {str(e)}: " \
                  f"Can't proceed after querying MPI for VA Profile ID for {notification_id}. " \
                  "Stopping execution of following tasks. Notification has been updated to permanent-failure."
        current_app.logger.warning(message)
        self.request.chain = None
        notifications_dao.update_notification_status_by_id(
            notification_id, NOTIFICATION_PERMANENT_FAILURE, status_reason=e.failure_reason
        )
        check_and_queue_callback_task(notification)
        raise NotificationPermanentFailureException(message) from e

    except Exception as e:
        message = f"Failed to retrieve VA Profile ID from MPI for notification: {notification_id} " \
                  "Notification has been updated to technical-failure"
        current_app.logger.exception(message)

        status_reason = e.failure_reason if hasattr(e, 'failure_reason') else 'Unknown error from MPI'
        notifications_dao.update_notification_status_by_id(
            notification_id, NOTIFICATION_TECHNICAL_FAILURE, status_reason=status_reason
        )
        raise NotificationTechnicalFailureException(message) from e
