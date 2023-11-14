from flask import current_app
from app.config import QueueNames
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, PUSH_TYPE, SMS_TYPE, Template
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    send_to_queue_for_recipient_info_based_on_recipient_identifier
)


def send_notification_bypass_route(
        service_id: str,
        template: Template,
        notification_type: str,
        recipient: str = None,
        personalisation: dict = None,
        sms_sender_id: str = None,
        recipient_id: dict = None,
        api_key_type: str = KEY_TYPE_NORMAL):

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=recipient,
        service_id=service_id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=None,
        key_type=api_key_type,
        recipient_identifier=recipient_id,
        sms_sender_id=sms_sender_id,
    )

    if notification_type == SMS_TYPE:
        q = QueueNames.SEND_SMS
    elif notification_type == EMAIL_TYPE:
        q = QueueNames.SEND_EMAIL
    elif notification_type == PUSH_TYPE:
        q = QueueNames.NOTIFY  # there's no push queue?
    else:
        q = QueueNames.NOTIFY

    current_app.logger.info(
        'sending %s notification with send_notification_bypass_route, notification id %s',
        notification_type, notification.id
    )

    if recipient is not None:
        send_to_queue_for_recipient_info_based_on_recipient_identifier(
            notification=notification,
            id_type=recipient['id_type'],
            id_value=recipient['id_value'],
            communication_item_id=template.communication_item_id,
            onsite_enabled=False
        )
    else:
        send_notification_to_queue(
            notification=notification,
            research_mode=False,
            queue=q,
            recipient_id_type=recipient_id.get('id_type') if recipient_id else None,
            sms_sender_id=sms_sender_id
        )
