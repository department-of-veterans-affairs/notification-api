from flask import current_app
from app import notify_celery
from app import va_onsite_client


@notify_celery.task(name='send-va-onsite-notification-task')
def send_va_onsite_notification_task(
    va_profile_id: str,
    template_id: str,
    onsite_enabled: bool = False,
):
    """
    POST a notification to VA_Onsite.
    """

    current_app.logger.info(
        'Calling va_onsite_notification_task with va_profile_id: %s\ntemplate_id: %s\nonsite_notification set to: %s',
        va_profile_id,
        template_id,
        onsite_enabled,
    )

    if onsite_enabled and va_profile_id:
        data = {'onsite_notification': {'template_id': template_id, 'va_profile_id': va_profile_id}}

        # This method catches exceptions.  It should never disrupt execution of the Celery task chain.
        va_onsite_client.post_onsite_notification(data)
