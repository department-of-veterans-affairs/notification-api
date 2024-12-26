from dataclasses import dataclass
from uuid import uuid4

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app.constants import SMS_TYPE
from app.dao.service_sms_sender_dao import dao_get_service_sms_sender_by_id
from app.models import (
    Service,
    Template,
)
from app.notifications.send_notifications import send_notification_bypass_route
from app.va.identifier import IdentifierType


@dataclass
class DynamoRecord:
    participant_id: str
    payment_amount: str
    vaprofile_id: str


class CompPenMsgHelper:
    dynamodb_table = None

    def __init__(self, dynamodb_table_name: str) -> None:
        """
        This class is a collection of helper methods to facilitate the delivery of schedule Comp and Pen notifications.

        :param dynamodb_table_name (str): the name of the dynamodb table for the db operations, required
        """
        self.dynamodb_table_name = dynamodb_table_name

    def batch_send_comp_and_pen_sms(
        self,
        service: Service,
        template: Template,
        sms_sender_id: str,
        comp_and_pen_messages: list[DynamoRecord],
        perf_to_number: str,
    ) -> None:
        """
        Sends scheduled SMS notifications to recipients based on the provided parameters.

        Args:
            :param service (Service): The service used to send the SMS notifications.
            :param template (Template): The template used for the SMS notifications.
            :param sms_sender_id (str): The ID of the SMS sender.
            :param comp_and_pen_messages (list[dict[str, int | float]]): A list of dictionaries from the dynamodb
                table containing the details needed to send the messages.
            :param perf_to_number (str): The recipient's phone number.

        Raises:
            Exception: If there is an error while sending the SMS notification.
        """
        try:
            reply_to_text = dao_get_service_sms_sender_by_id(service.id, sms_sender_id).sms_sender
        except (NoResultFound, AttributeError):
            current_app.logger.exception('Unable to send comp and pen notifications due to improper sms_sender')
            raise

        for item in comp_and_pen_messages:
            current_app.logger.debug('sending - record from dynamodb: %s', item.participant_id)

            # Use perf_to_number as the recipient if available. Otherwise, use vaprofile_id as recipient_item.
            recipient = perf_to_number
            recipient_item = (
                None
                if perf_to_number is not None
                else {
                    'id_type': IdentifierType.VA_PROFILE_ID.value,
                    'id_value': item.vaprofile_id,
                }
            )

            try:
                # call generic method to send messages
                send_notification_bypass_route(
                    service=service,
                    template=template,
                    notification_type=SMS_TYPE,
                    reply_to_text=reply_to_text,
                    personalisation={'amount': item.payment_amount},
                    sms_sender_id=sms_sender_id,
                    recipient=recipient,
                    recipient_item=recipient_item,
                    notification_id=uuid4(),
                )
            except Exception:
                current_app.logger.exception(
                    'Error attempting to send Comp and Pen notification with '
                    'send_comp_and_pen_sms | record from dynamodb: %s',
                    item.participant_id,
                )
            else:
                if perf_to_number is not None:
                    current_app.logger.info(
                        'Notification sent using Perf simulated number %s instead of vaprofile_id', perf_to_number
                    )

                current_app.logger.info('Notification sent to queue for record from dynamodb: %s', item.participant_id)
