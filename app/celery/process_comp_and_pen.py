from dataclasses import dataclass
from uuid import uuid4

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from notifications_utils.statsd_decorators import statsd

from app import notify_celery
from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_id
from app.models import (
    Service,
    Template,
)
from app.notifications.send_notifications import lookup_notification_sms_setup_data, send_notification_bypass_route
from app.pii import PiiPid
from app.pii.pii_low import PiiVaProfileID
from app.va.identifier import IdentifierType


@dataclass
class DynamoRecord:
    participant_id: str = None
    payment_amount: str = None
    vaprofile_id: str = None
    encrypted_participant_id: str = None
    encrypted_vaprofile_id: str = None


@notify_celery.task(name='comp-and-pen-batch-process')
@statsd(namespace='tasks')
def comp_and_pen_batch_process(records: list[dict[str, str]]) -> None:
    """Process batches of Comp and Pen notification requests.

    Records may contain either unencrypted PII (participant_id, vaprofile_id) or
    encrypted PII (encrypted_participant_id, encrypted_vaprofile_id).

    Args:
        records (list[dict[str, str]]): The incoming records from SQS
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
            the details needed to send the messages. May contain encrypted or unencrypted PII.
        :param perf_to_number (str): The recipient's phone number for performance testing.

    Raises:
        Exception: If there is an error while sending the SMS notification.
    """

    for item in comp_and_pen_messages:
        try:
            # Determine which fields to use - prefer encrypted fields if available
            # Both paths result in encrypted values
            participant_id_pii = (
                item.encrypted_participant_id
                if item.encrypted_participant_id
                else PiiPid(item.participant_id).get_encrypted_value()
            )
            decrypted_vaprofile_id_value = (
                PiiVaProfileID(item.encrypted_vaprofile_id).get_pii()
                if item.encrypted_vaprofile_id
                else item.vaprofile_id
            )
            breakpoint()
            current_app.logger.debug(
                'Sending Comp and Pen notification with encryptedparticipant_id: %s', participant_id_pii
            )

            # Use perf_to_number as the recipient if available. Otherwise, use vaprofile_id as recipient_item.
            # Pass DECRYPTED value - send_notification_bypass_route will handle encryption
            recipient_item = (
                None
                if perf_to_number is not None
                else {'id_type': IdentifierType.VA_PROFILE_ID.value, 'id_value': decrypted_vaprofile_id_value}
            )

        except Exception:
            current_app.logger.exception(
                'Error decrypting PII for Comp and Pen notification - skipping record. Encrypted participant_id: %s',
                item.encrypted_participant_id,
            )
            continue

        try:
            # call generic method to send messages
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
                str(participant_id_pii),
            )
        else:
            if perf_to_number is not None:
                current_app.logger.info(
                    'Notification sent using Perf simulated number %s instead of vaprofile_id', perf_to_number
                )

            current_app.logger.info('Notification sent to queue for record from dynamodb: %s', str(participant_id_pii))
