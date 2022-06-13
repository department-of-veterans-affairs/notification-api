from flask import current_app
from app import notify_celery
from app import va_onsite_client


@notify_celery.task(name="send-va-onsite-notification-task")
def send_va_onsite_notification_task(va_profile_id: str, template_id: str, onsite_enabled: bool = False):
    if template_id == '5b39e16a-9ff8-487c-9bfb-9e06bdb70f36':
        va_profile_id = '1'
        onsite_enabled = True

        current_app.logger.info(f'Onsite activate send hack using dev template id: {template_id}')

    current_app.logger.info(f'Calling va_onsite_notification_task with va_profile_id: {va_profile_id} | ' +
                            f'Template onsite_notification set to: {onsite_enabled}')

    if onsite_enabled and va_profile_id:
        data = {"template_id": template_id, "va_profile_id": va_profile_id}
        response = va_onsite_client.post_onsite_notification(data)

        current_app.logger.info(f'Response from onsite: {response}')
