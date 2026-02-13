from dataclasses import dataclass
from uuid import uuid4

from cryptography.fernet import InvalidToken
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from notifications_utils.statsd_decorators import statsd

from app import notify_celery
from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_id
from app.feature_flags import is_feature_enabled, FeatureFlag
from app.models import (
    Service,
    Template,
)
from app.notifications.send_notifications import lookup_notification_sms_setup_data, send_notification_bypass_route
from app.pii import PiiPid, PiiVaProfileID
from app.va.identifier import IdentifierType


@dataclass
class DynamoRecord:
    payment_amount: str
    participant_id: str = ''
    vaprofile_id: str = ''
    encrypted_participant_id: str = ''
    encrypted_vaprofile_id: str = ''


@notify_celery.task(name='comp-and-pen-batch-process')
@statsd(namespace='tasks')
def comp_and_pen_batch_process(records: list[dict[str, str]]) -> None:
    """Process batches of Comp and Pen notification requests.  Note that the records contain plain text
    or encrypted recipient identifiers, which are PII.

    Args:
        records (list[dict[str, str]]): The incoming records
    """

    current_app.logger.debug('comp_and_pen_batch_process started for %s records.', len(records))

    try:
        # Grab all the necessary data
        service, template, sms_sender_id = lookup_notification_sms_setup_data(
            current_app.config['COMP_AND_PEN_SERVICE_ID'],
            current_app.config['COMP_AND_PEN_TEMPLATE_ID'],
            current_app.config['COMP_AND_PEN_SMS_SENDER_ID'],
        )
        reply_to_text = dao_get_service_sms_sender_by_id(str(service.id), str(sms_sender_id)).sms_sender
    except (AttributeError, NoResultFound, ValueError):
        current_app.logger.exception('Unable to send comp and pen notifications due to improper configuration')
        raise

    _send_comp_and_pen_sms(
        service,
        template,
        sms_sender_id,
        reply_to_text,
        [DynamoRecord(**item) for item in records],
        current_app.config['COMP_AND_PEN_PERF_TO_NUMBER'],
    )


def _resolve_pii_for_comp_and_pen(item: DynamoRecord) -> tuple[str | PiiPid, str | PiiVaProfileID]:
    """Resolve participant_id and vaprofile_id based on the PII feature flag and field availability.

    The 4 scenarios:
        1. PII_ENABLED FF ON  + encrypted fields → use encrypted data through system (wrap as Pii, already encrypted)
        2. PII_ENABLED FF OFF + encrypted fields → decrypt to use in rest of path (plain strings)
        3. PII_ENABLED FF ON  + unencrypted fields → encrypt the data (wrap as Pii)
        4. PII_ENABLED FF OFF + unencrypted fields → use unencrypted data through system (plain strings)

    Args:
        item: The DynamoRecord to resolve PII for.

    Returns:
        A tuple of (resolved_participant_id, resolved_vaprofile_id).
        When PII_ENABLED, these are Pii subclass instances. Otherwise, plain strings.

    Raises:
        ValueError: If required fields are missing or decryption fails.
    """

    # Encrypted fields must be both present or both absent — the Glue script should always send them as a pair
    if bool(item.encrypted_participant_id) != bool(item.encrypted_vaprofile_id):
        raise ValueError(
            'DynamoRecord has mismatched encrypted fields: '
            f'encrypted_participant_id={"present" if item.encrypted_participant_id else "missing"}, '
            f'encrypted_vaprofile_id={"present" if item.encrypted_vaprofile_id else "missing"}. '
            'Both must be provided or both must be empty.'
        )

    # Prefer encrypted fields if available
    raw_pid = item.encrypted_participant_id or item.participant_id
    raw_vaprofile = item.encrypted_vaprofile_id or item.vaprofile_id
    is_encrypted = bool(item.encrypted_participant_id)

    if not raw_pid or not raw_vaprofile:
        raise ValueError('DynamoRecord missing required participant_id or vaprofile_id')

    pii_enabled = is_feature_enabled(FeatureFlag.PII_ENABLED)

    if pii_enabled and is_encrypted:
        # Scenario 1: PII_ENABLED FF ON + encrypted fields → wrap as Pii with is_encrypted=True
        return PiiPid(raw_pid, is_encrypted=True), PiiVaProfileID(raw_vaprofile, is_encrypted=True)

    elif not pii_enabled and is_encrypted:
        # Scenario 2: PII_ENABLED FF OFF + encrypted fields → decrypt to plain strings
        return PiiPid(raw_pid, is_encrypted=True).get_pii(), PiiVaProfileID(raw_vaprofile, is_encrypted=True).get_pii()

    elif pii_enabled and not is_encrypted:
        # Scenario 3: PII_ENABLED FF ON + unencrypted fields → encrypt by wrapping in Pii
        return PiiPid(raw_pid), PiiVaProfileID(raw_vaprofile)

    else:
        # Scenario 4: PII_ENABLED FF OFF + unencrypted fields → use as-is
        return raw_pid, raw_vaprofile


def _send_comp_and_pen_sms(
    service: Service,
    template: Template,
    sms_sender_id: str,
    reply_to_text: str,
    comp_and_pen_messages: list[DynamoRecord],
    perf_to_number: str,
) -> None:
    """
    Sends scheduled SMS notifications to recipients based on the provided parameters.

    Args:
        :param service (Service): The service used to send the SMS notifications.
        :param template (Template): The template used for the SMS notifications.
        :param sms_sender_id (str): The ID of the SMS sender.
        :param reply_to_text (str): The text a Veteran can reply to.
        :param comp_and_pen_messages (list[DynamoRecord]): A list of DynamoRecord from the dynamodb table containing
            the details needed to send the messages.  This includes PII.
        :param perf_to_number (str): The recipient's phone number.

    Raises:
        Exception: If there is an error while sending the SMS notification.
    """

    for item in comp_and_pen_messages:
        try:
            resolved_pid, resolved_vaprofile = _resolve_pii_for_comp_and_pen(item)
        except (ValueError, InvalidToken) as e:
            raw_encrypted_pid = item.encrypted_participant_id

            current_app.logger.error(
                'Error resolving PII for Comp and Pen record with encrypted participant_id: %s with %s',
                raw_encrypted_pid if raw_encrypted_pid else 'unknown or unencrypted participant_id',
                str(e),
            )
            continue

        except Exception:
            current_app.logger.error('Unexpected error resolving PII for Comp and Pen record')
            continue

        log_pid = resolved_pid if isinstance(resolved_pid, PiiPid) else PiiPid(str(resolved_pid))
        current_app.logger.debug(
            'Sending Comp and Pen SMS Notification with encrypted participant_id: %s', str(log_pid)
        )

        # Use perf_to_number as the recipient if available. Otherwise, use vaprofile_id as recipient_item.
        recipient_item = (
            None
            if perf_to_number is not None
            else {
                'id_type': IdentifierType.VA_PROFILE_ID.value,
                'id_value': resolved_vaprofile,
            }
        )

        try:
            send_notification_bypass_route(
                service=service,
                template=template,
                reply_to_text=reply_to_text,
                personalisation={'amount': item.payment_amount},
                sms_sender_id=sms_sender_id,
                recipient=perf_to_number,
                recipient_item=recipient_item,
                notification_id=uuid4(),
            )
        except Exception:
            current_app.logger.exception(
                'Error attempting to send Comp and Pen notification with '
                'send_comp_and_pen_sms | record from dynamodb: %s',
                str(log_pid),
            )
        else:
            if perf_to_number is not None:
                current_app.logger.info(
                    'Notification sent using Perf simulated number %s instead of vaprofile_id', perf_to_number
                )

            current_app.logger.info('Notification sent to queue for record from dynamodb: %s', str(log_pid))
