from flask import current_app
from app.config import QueueNames
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, SMS_TYPE, Service, Template
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    send_to_queue_for_recipient_info_based_on_recipient_identifier
)


def send_notification_bypass_route(
        service: Service,
        template: Template,
        notification_type: str,
        recipient: str = None,
        personalisation: dict = None,
        sms_sender_id: str = None,
        recipient_item: dict = None,
        api_key_type: str = KEY_TYPE_NORMAL
):

    if recipient is None and recipient_item is None:
        current_app.logger.critical(
            'Programming error attempting to use send_notification_bypass_route, both recipient and recipient_item are '
            'None. Please check the code calling this function to ensure one of these fields is populated properly.'
        )

        return

    # Use the service's default sms_sender if applicable
    if notification_type == SMS_TYPE and sms_sender_id is None:
        sms_sender_id = service.get_default_sms_sender_id()

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=recipient,
        service_id=service.id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=None,
        key_type=api_key_type,
        recipient_identifier=recipient_item,
        sms_sender_id=sms_sender_id,
    )

    if recipient_item is not None:
        current_app.logger.info(
            'sending %s notification with send_notification_bypass_route via '
            'send_to_queue_for_recipient_info_based_on_recipient_identifier, notification id %s',
            notification_type, notification.id
        )

        send_to_queue_for_recipient_info_based_on_recipient_identifier(
            notification=notification,
            id_type=recipient_item['id_type'],
            id_value=recipient_item['id_value'],
            communication_item_id=template.communication_item_id,
            onsite_enabled=False
        )

    else:
        if notification_type == SMS_TYPE:
            q = QueueNames.SEND_SMS
        elif notification_type == EMAIL_TYPE:
            q = QueueNames.SEND_EMAIL
        else:
            q = QueueNames.NOTIFY

        current_app.logger.info(
            'sending %s notification with send_notification_bypass_route via send_notification_to_queue, '
            'notification id %s', notification_type, notification.id
        )

        send_notification_to_queue(
            notification=notification,
            research_mode=False,
            queue=q,
            recipient_id_type=recipient_item.get('id_type') if recipient_item else None,
            sms_sender_id=sms_sender_id
        )
