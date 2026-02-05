from dataclasses import dataclass
from celery import Task
import iso8601

from celery.exceptions import Retry
from datetime import datetime, timedelta
from enum import Enum
from flask import (
    current_app,
    json,
)
from json import JSONDecodeError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.sql.dml import Update

from notifications_utils.statsd_decorators import statsd

from app import notify_celery, statsd_client
from app.celery.common import log_notification_total_time
from app.celery.exceptions import NonRetryableException
from app.celery.send_va_profile_notification_status_tasks import check_and_queue_va_profile_notification_status_callback
from app.celery.service_callback_tasks import publish_complaint
from app.config import QueueNames
from app.constants import (
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENDING,
    NOTIFICATION_TEMPORARY_FAILURE,
    SES_PROVIDER,
    STATUS_REASON_RETRYABLE,
    STATUS_REASON_UNREACHABLE,
)
from app.clients.email.aws_ses import get_aws_responses
from app.dao import notifications_dao
from app.feature_flags import FeatureFlag, is_feature_enabled
from app.models import Notification, NotificationHistory
from app.notifications.notifications_ses_callback import (
    determine_notification_bounce_type,
    handle_ses_complaint,
)
from app.celery.service_callback_tasks import check_and_queue_callback_task


class SesEventType(Enum):
    BOUNCE = 'Bounce'
    COMPLAINT = 'Complaint'
    DELIVERY = 'Delivery'
    OPEN = 'Open'
    SEND = 'Send'
    RENDERING_FAILURE = 'Rendering Failure'


@dataclass
class EmailStatusRecord:
    notification: Notification | NotificationHistory
    status: str
    status_reason: str | None
    provider: str
    price_millicents: float = 0.0
    provider_updated_at: datetime | None = None


@dataclass
class SesBounce:
    bounce_type: str
    bounce_sub_type: str | None = None


@dataclass
class SesComplaint:
    feedback_type: str | None
    feedback_id: str | None
    timestamp: datetime | None


@dataclass
class SesDelivered:
    timestamp: datetime | None


@dataclass
class SesOpen:
    timestamp: datetime | None


@dataclass
class SesSend:
    timestamp: datetime | None


@dataclass
class SesRenderingFailure:
    timestamp: datetime | None


SesEvent = SesBounce | SesComplaint | SesDelivered | SesOpen | SesSend | SesRenderingFailure


@dataclass
class SesResponse:
    """Represents all the relevant fields of an SES response."""

    event_type: SesEventType
    reference: str
    mail: 'SesMail'
    event: SesEvent


@dataclass
class SesMail:
    timestamp: datetime
    reference: str


@notify_celery.task(bind=True, name='process-ses-result', max_retries=5, default_retry_delay=300)
@statsd(namespace='tasks')
def process_ses_results(
    task: Task,
    celery_envelope: str,
):
    current_app.logger.debug('Incoming SES response: %s', celery_envelope)

    if is_feature_enabled(FeatureFlag.EMAIL_DELIVERY_STATUS_OVERHAUL):
        # This is a general outline
        ses_response: SesResponse | None = _validate_response(celery_envelope)
        if ses_response is None:
            # unknown event types are logged as a warning
            return
        db_notification: Notification | NotificationHistory = _get_notification(ses_response.reference)
        current_app.logger.info(
            'SES details for notification: %s | current status: %s | event_type: %s',
            db_notification.id,
            db_notification.status,
            ses_response.event_type,
            # Add the rest
        )
        status_record, where_clause = _handle_response(ses_response, db_notification)
        notification: Notification = _update_notification_where(status_record, where_clause)

        # log status_record details
        _queue_callbacks(notification)
        log_notification_total_time(
            notification.id,
            notification.created_at,
            notification.status,
            SES_PROVIDER,
        )
    else:
        return _process_ses_results(task, celery_envelope, task.request.retries)


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a naive datetime.

    Args:
        value (str): ISO-8601 timestamp string.

    Returns:
        datetime: Parsed timestamp with tzinfo stripped.

    Raises:
        NonRetryableException: If the timestamp is invalid.
    """
    try:
        return iso8601.parse_date(value).replace(tzinfo=None)
    except (iso8601.ParseError, TypeError, ValueError) as e:
        raise NonRetryableException('Invalid SES timestamp') from e


def _parse_optional_timestamp(value: str | None) -> datetime | None:
    """Parse an optional ISO-8601 timestamp.

    Args:
        value (str | None): Timestamp string or None.

    Returns:
        datetime | None: Parsed timestamp or None.
    """
    if value is None:
        return None
    return _parse_timestamp(value)


def _build_event(event_type: SesEventType, ses_event: dict) -> SesEvent:
    """Build a typed SES event payload from the raw event dict.

    SES event payload examples:
    https://docs.aws.amazon.com/ses/latest/dg/event-publishing-retrieving-sns-examples.html

    Args:
        event_type (SesEventType): SES event type.
        ses_event (dict): Raw SES event payload.

    Returns:
        SesEvent: Parsed event dataclass.

    Raises:
        NonRetryableException: If required fields are missing.
    """
    if event_type == SesEventType.BOUNCE:
        bounce = ses_event.get('bounce')
        if not bounce or not bounce.get('bounceType'):
            raise NonRetryableException('SES bounce missing bounceType')
        return SesBounce(
            bounce_type=bounce['bounceType'],
            bounce_sub_type=bounce.get('bounceSubType'),
        )
    if event_type == SesEventType.COMPLAINT:
        complaint = ses_event.get('complaint')
        if complaint is None:
            raise NonRetryableException('SES complaint missing complaint data')
        return SesComplaint(
            feedback_type=complaint.get('complaintFeedbackType'),
            feedback_id=complaint.get('feedbackId'),
            timestamp=_parse_optional_timestamp(complaint.get('timestamp')),
        )
    if event_type == SesEventType.DELIVERY:
        delivery = ses_event.get('delivery', {})
        return SesDelivered(timestamp=_parse_optional_timestamp(delivery.get('timestamp')))
    if event_type == SesEventType.OPEN:
        open_event = ses_event.get('open', {})
        return SesOpen(timestamp=_parse_optional_timestamp(open_event.get('timestamp')))
    if event_type == SesEventType.SEND:
        send = ses_event.get('send', {})
        return SesSend(timestamp=_parse_optional_timestamp(send.get('timestamp')))
    if event_type == SesEventType.RENDERING_FAILURE:
        failure = ses_event.get('failure', {})
        return SesRenderingFailure(timestamp=_parse_optional_timestamp(failure.get('timestamp')))
    raise NonRetryableException('Unsupported SES event type')


def _ses_log_context(ses_event: dict | None) -> dict:
    """Build log context from an SES event dict."""
    if not isinstance(ses_event, dict):
        return {}
    mail = ses_event.get('mail') or {}
    return {
        'event_type': ses_event.get('eventType'),
        'message_id': mail.get('messageId'),
        'mail_timestamp': mail.get('timestamp'),
    }


def _get_message(celery_envelope: dict) -> str:
    """Extract the SES Message string from a Celery envelope.

    Args:
        celery_envelope (dict): Celery task envelope.

    Returns:
        str: SES message payload string.

    Raises:
        NonRetryableException: If Message is missing.
    """
    message = celery_envelope.get('Message')
    if message is None:
        current_app.logger.error('SES response missing Message. envelope_fields=%s', list(celery_envelope.keys()))
        raise NonRetryableException('Unable to find "Message" in SES response')
    return message


def _parse_ses_event(message: str) -> dict:
    """Parse the SES message JSON into a dict.

    Args:
        message (str): SES message payload string.

    Returns:
        dict: Parsed SES event data.

    Raises:
        NonRetryableException: If JSON is invalid or not an object.
    """
    try:
        ses_event = json.loads(message)
    except JSONDecodeError as e:
        current_app.logger.error('Error decoding SES results.')
        raise NonRetryableException from e

    if not isinstance(ses_event, dict):
        current_app.logger.error('SES response is not a JSON object. type=%s', type(ses_event).__name__)
        raise NonRetryableException('SES response is not a JSON object')

    return ses_event


def _get_event_type_value(ses_event: dict) -> str:
    """Return the SES eventType string.

    Args:
        ses_event (dict): Parsed SES event data.

    Returns:
        str: eventType value.

    Raises:
        NonRetryableException: If eventType is missing.
    """
    event_type_value = ses_event.get('eventType')
    if event_type_value is None:
        current_app.logger.error('SES response missing eventType. context=%s', _ses_log_context(ses_event))
        raise NonRetryableException('SES response missing eventType')
    return event_type_value


def _get_event_type(event_type_value: str) -> SesEventType | None:
    """Map an eventType string to SesEventType.

    Args:
        event_type_value (str): SES eventType value.

    Returns:
        SesEventType | None: Enum value or None if unsupported.
    """
    try:
        return SesEventType(event_type_value)
    except ValueError:
        # Legacy behavior: unknown event types are logged and ignored.
        current_app.logger.error('Unsupported SES eventType received. eventType=%s', event_type_value)
        statsd_client.incr('clients.ses.status_update.ignored')
        return None


def _get_mail(ses_event: dict, event_type_value: str) -> dict:
    """Return the mail block from the SES event.

    Args:
        ses_event (dict): Parsed SES event data.
        event_type_value (str): SES eventType value for logging.

    Returns:
        dict: mail block payload.

    Raises:
        NonRetryableException: If mail is missing.
    """
    mail = ses_event.get('mail')
    if not mail:
        current_app.logger.error('SES response missing mail. eventType=%s', event_type_value)
        raise NonRetryableException('SES response missing mail')
    return mail


def _get_reference(ses_event: dict, mail: dict) -> str:
    """Return the SES messageId reference from mail.

    Args:
        ses_event (dict): Parsed SES event data.
        mail (dict): mail block payload.

    Returns:
        str: messageId reference.

    Raises:
        NonRetryableException: If messageId is missing.
    """
    reference = mail.get('messageId')
    if not reference:
        current_app.logger.error('SES response missing mail.messageId. context=%s', _ses_log_context(ses_event))
        raise NonRetryableException('SES response missing mail.messageId')
    return reference


def _get_mail_timestamp(ses_event: dict, mail: dict) -> datetime:
    """Parse the mail timestamp from the SES event.

    Args:
        ses_event (dict): Parsed SES event data.
        mail (dict): mail block payload.

    Returns:
        datetime: Parsed mail timestamp.

    Raises:
        NonRetryableException: If the timestamp is missing or invalid.
    """
    mail_timestamp = mail.get('timestamp')
    if not mail_timestamp:
        current_app.logger.error('SES response missing mail.timestamp. context=%s', _ses_log_context(ses_event))
        raise NonRetryableException('SES response missing mail.timestamp')

    try:
        return _parse_timestamp(mail_timestamp)
    except NonRetryableException:
        current_app.logger.error('SES response has invalid mail.timestamp. context=%s', _ses_log_context(ses_event))
        raise


def _get_event(event_type: SesEventType, ses_event: dict) -> SesEvent:
    """Build a typed event and emit context on failure.

    Args:
        event_type (SesEventType): SES event type.
        ses_event (dict): Parsed SES event data.

    Returns:
        SesEvent: Parsed event dataclass.

    Raises:
        NonRetryableException: If building the event fails.
    """
    try:
        return _build_event(event_type, ses_event)
    except NonRetryableException:
        current_app.logger.error('Unable to build SES event. context=%s', _ses_log_context(ses_event))
        raise


def _translate_ses_response(celery_envelope: dict) -> SesResponse | None:
    """Translate a Celery envelope into a SesResponse.

    Args:
        celery_envelope (dict): Celery task envelope.

    Returns:
        SesResponse | None: Parsed response or None if unsupported.
    """
    message = _get_message(celery_envelope)
    ses_event = _parse_ses_event(message)
    event_type_value = _get_event_type_value(ses_event)
    event_type = _get_event_type(event_type_value)
    if event_type is None:
        current_app.logger.warning(
            'Unsupported SES eventType received. context=%s',
            _ses_log_context(ses_event),
        )
        # intentionally return early here to ignore unsupported event types.
        return None
    mail = _get_mail(ses_event, event_type_value)
    reference = _get_reference(ses_event, mail)
    mail_timestamp_dt = _get_mail_timestamp(ses_event, mail)
    event = _get_event(event_type, ses_event)
    return SesResponse(
        event_type=event_type,
        reference=reference,
        mail=SesMail(timestamp=mail_timestamp_dt, reference=reference),
        event=event,
    )


def _validate_response(celery_envelope: dict) -> SesResponse | None:
    """Validate a Celery envelope and return a parsed response.

    Emits warning log for unsupported event types and raises on invalid payloads.
    Emits statsd success/error metrics for validation outcomes.

    Args:
        celery_envelope (dict): Celery task envelope.

    Returns:
        SesResponse | None: Parsed response or None if unsupported.
    """
    try:
        response = _translate_ses_response(celery_envelope)
    except NonRetryableException:
        statsd_client.incr('clients.ses.status_update.error')
        raise
    except Exception:
        current_app.logger.exception('Unexpected error validating SES response')
        statsd_client.incr('clients.ses.status_update.error')
        raise

    if response is None:
        return None
    statsd_client.incr('clients.ses.status_update.success')
    return response


def _get_notification(reference) -> Notification | NotificationHistory:
    try:
        notification: Notification | NotificationHistory = notifications_dao.dao_get_notification_history_by_reference(
            reference
        )
    except (MultipleResultsFound, NoResultFound, SQLAlchemyError):
        current_app.logger.exception('Unable to find SES reference: %s', reference)
        raise

    return notification


def _handle_response(
    ses_response: SesResponse, notification: Notification | NotificationHistory
) -> tuple[EmailStatusRecord, Update]:
    # https://docs.aws.amazon.com/ses/latest/dg/event-publishing-retrieving-sns-examples.html#event-publishing-retrieving-sns-open
    # All should use one DAO update function with a WHERE clause similar to sms_conditions
    # The WHERE clause is made in each event handler and passes it to the update function
    # The alternative is one big clause, or duplicating the call each time
    if ses_response.event_type == SesEventType.BOUNCE:
        status_record, where_clause = _handle_bounce_event(ses_response, notification)
    elif ses_response.event_type == SesEventType.COMPLAINT:
        status_record, where_clause = _handle_complaint_event(ses_response, notification)
    elif ses_response.event_type == SesEventType.DELIVERY:
        status_record, where_clause = _handle_delivered_event(ses_response, notification)
    elif ses_response.event_type == SesEventType.OPEN:
        status_record, where_clause = _handle_open_event(ses_response, notification)
    elif ses_response.event_type == SesEventType.SEND:
        status_record, where_clause = _handle_send_event(ses_response, notification)
    elif ses_response.event_type == SesEventType.RENDERING_FAILURE:
        status_record, where_clause = _handle_rendering_failure_event(ses_response, notification)
    return status_record, where_clause


def _handle_bounce_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Hard bounces always overrides any status. Soft bounces do not update final states (delivered/perm fail)
    # status_record = EmailStatusRecord(<data>)
    # status_record.where_clause = update(...).where(...).values(...)
    ...


def _handle_complaint_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Complaints always override any status.
    ...


def _handle_delivered_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Delivered updates for all other than perm failure.
    # Track metric for OCTO OKR 1.2
    ...


def _handle_open_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Metric tracking
    ...


def _handle_send_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Metric tracking, this has left AWS
    ...


def _handle_rendering_failure_event(ses_response: SesResponse) -> EmailStatusRecord:
    # Permanent failure, critical exception needs to be raised so we can raise with the business
    ...


def _update_notification_where(status_record: EmailStatusRecord, stmt: Update) -> Notification:
    # Updates the Notification table based on status_record.where_clause, returns the current notification object
    ...


def _queue_callbacks(notification):
    check_and_queue_callback_task(notification)
    check_and_queue_va_profile_notification_status_callback(notification)


def _process_ses_results(task, response, celery_retry_count):  # noqa: C901 (too complex 20 > 10)
    current_app.logger.debug('Full SES result response: %s', response)

    try:
        ses_message = json.loads(response['Message'])
    except JSONDecodeError:
        current_app.logger.exception('Error decoding SES results: full response data: %s', response)
        return

    reference = ses_message.get('mail', {}).get('messageId')
    if not reference:
        current_app.logger.warning(
            'SES complaint: unable to lookup notification, messageId (reference) was None | ses_message: %s',
            ses_message,
        )
        return

    notification_type = ses_message.get('eventType')
    if notification_type is None:
        current_app.logger.warning(
            'SES response: nothing to process, eventType was None | ses_message: %s',
            ses_message,
        )
        return

    try:
        if notification_type == 'Bounce':
            # Bounces have ran their course with AWS and should be considered done. Clients can retry soft bounces.
            notification_type = determine_notification_bounce_type(notification_type, ses_message)
        elif notification_type == 'Complaint':
            try:
                notification = notifications_dao.dao_get_notification_history_by_reference(reference)
            except Exception:
                # we expect results or no results but it could be multiple results
                message_time = iso8601.parse_date(ses_message['mail']['timestamp']).replace(tzinfo=None)
                if datetime.utcnow() - message_time < timedelta(minutes=5):
                    task.retry(queue=QueueNames.RETRY)
                else:
                    current_app.logger.warning('SES complaint: notification not found | reference: %s', reference)
                return

            complaint, recipient_email = handle_ses_complaint(ses_message, notification)
            publish_complaint(complaint, notification, recipient_email)
            return

        aws_response_dict = get_aws_responses(notification_type)

        # This is the prospective, updated status.
        incoming_status = aws_response_dict['notification_status']

        try:
            notification = notifications_dao.dao_get_notification_by_reference(reference)
        except Exception:
            # we expect results or no results but it could be multiple results
            message_time = iso8601.parse_date(ses_message['mail']['timestamp']).replace(tzinfo=None)
            if datetime.utcnow() - message_time < timedelta(minutes=5):
                current_app.logger.info(
                    'Retrying SES notification lookup for reference: %s. Sending to retry queue %s',
                    reference,
                    QueueNames.RETRY,
                )
                task.retry(queue=QueueNames.RETRY)
            else:
                current_app.logger.warning(
                    'notification not found for reference: %s (update to %s)', reference, incoming_status
                )
            return

        provider_updated_at = iso8601.parse_date(ses_message['mail']['timestamp']).replace(tzinfo=None)
        if provider_updated_at:
            current_app.logger.debug(
                'Updating notification %s provider_updated_at to %s', notification.id, provider_updated_at
            )
            notifications_dao.dao_update_provider_updated_at(
                notification_id=notification.id, provider_updated_at=provider_updated_at
            )

        if celery_retry_count > 0:
            db_retry_count = notifications_dao.dao_increment_notification_retry_count(notification.id)
            current_app.logger.info(
                '_process_ses_results retry_attempt for notification %s, total retry_count now %s',
                notification.id,
                db_retry_count,
            )

        # Prevent regressing bounce status.  Note that this is a test of the existing status; not the new status.
        if notification.status_reason and (
            notification.status_reason == STATUS_REASON_UNREACHABLE
            or notification.status_reason == STATUS_REASON_RETRYABLE
        ):
            # async from AWS means we may get a delivered status after a bounce, in rare cases
            current_app.logger.warning(
                'Notification: %s was marked as a bounce, cannot be updated to: %s',
                notification.id,
                incoming_status,
            )
            return

        # Redact personalisation when an email is in a final state. An email may go from delivered to a bounce, but
        # that will not affect the redaction, as the email will not be retried.
        if incoming_status in (NOTIFICATION_DELIVERED, NOTIFICATION_PERMANENT_FAILURE):
            notification.personalisation = {k: '<redacted>' for k in notification.personalisation}

        # This is a test of the new status.  Is it a bounce?
        if incoming_status in (NOTIFICATION_TEMPORARY_FAILURE, NOTIFICATION_PERMANENT_FAILURE):
            # Add the failure status reason to the notification.
            if incoming_status == NOTIFICATION_PERMANENT_FAILURE:
                failure_reason = 'Failed to deliver email due to hard bounce'
                status_reason = STATUS_REASON_UNREACHABLE
            else:
                failure_reason = 'Temporarily failed to deliver email due to soft bounce'
                status_reason = STATUS_REASON_RETRYABLE

            notification.status_reason = status_reason
            notification.status = incoming_status

            current_app.logger.warning(
                '%s - %s - in process_ses_results for notification %s',
                incoming_status,
                failure_reason,
                notification.id,
            )

            notifications_dao.dao_update_notification(notification)
            check_and_queue_callback_task(notification)
            check_and_queue_va_profile_notification_status_callback(notification)

            return
        elif incoming_status == NOTIFICATION_DELIVERED:
            # Delivered messages should never have a status reason.
            notification.status_reason = None

        if notification.status not in (NOTIFICATION_SENDING, NOTIFICATION_PENDING):
            notifications_dao.duplicate_update_warning(notification, incoming_status)
            return

        notifications_dao._update_notification_status(notification=notification, status=incoming_status)

        if not aws_response_dict['success']:
            current_app.logger.info(
                'SES delivery failed: notification id %s and reference %s has error found. Status %s',
                notification.id,
                reference,
                aws_response_dict['message'],
            )
        else:
            current_app.logger.info(
                'SES callback return status of %s for notification: %s',
                incoming_status,
                notification.id,
            )

        log_notification_total_time(
            notification.id,
            notification.created_at,
            incoming_status,
            'ses',
        )

        check_and_queue_callback_task(notification)
        check_and_queue_va_profile_notification_status_callback(notification)

        return True

    except KeyError:
        current_app.logger.exception('AWS message malformed: full response data: %s', response)

    except Retry:
        raise

    except Exception:
        current_app.logger.exception(
            'Error processing SES results: reference: %s | notification_id: %s',
            notification.reference,
            notification.id,
        )
        task.retry(queue=QueueNames.RETRY)
