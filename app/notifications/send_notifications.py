

from app.config import QueueNames
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, PUSH_TYPE, SMS_TYPE
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.va.identifier import IdentifierType


def send_notification_bypass_route(
        service_id: str,
        template_id: str,
        notification_type: str,
        recipient: str = None,
        personalisation: list = None,
        sms_sender_id: str = None,
        recipient_id_type: IdentifierType = None,
        api_key_type: str = KEY_TYPE_NORMAL):

    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id(template_id)

    notification = persist_notification(
        template_id=template_id,
        template_version=template.version,
        recipient=recipient,
        service=service,
        service_id=service_id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=None,
        key_type=api_key_type,
        sms_sender_id=sms_sender_id,
    )

    if notification_type == SMS_TYPE:
        q = QueueNames.SEND_SMS
    elif notification_type == EMAIL_TYPE:
        q = QueueNames.SEND_EMAIL
    elif notification_type == PUSH_TYPE:
        q = QueueNames.NOTIFY
    else:
        q = QueueNames.NOTIFY

    send_notification_to_queue(
        notification=notification,
        research_mode=False,
        queue=q,
        recipient_id_type=recipient_id_type,
        sms_sender_id=sms_sender_id
    )
