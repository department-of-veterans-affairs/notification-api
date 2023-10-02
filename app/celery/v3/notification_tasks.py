# TODO - Should I continue using notify_celery?  It has side-effects.
from app import notify_celery
# from app.models import NOTIFICATION_PERMANENT_FAILURE


@notify_celery.task
def v3_process_notification(request_data: dict):
    """
    This is the first task used to process request data send to POST /v3/notification/(email|sms).  It performs
    additional, non-schema verifications that require database queries:

    1. The specified template exists is for the specified type of notification.
    2. ...etc...
    """

    # TODO - Query to get the template

    # Ensure the template type matches the given notification type.
    # TODO

    # Create the notification content using the template and personalization data.
    # TODO

    # Determine the provider.
    # Launch a new task to make an API call to the provider.
    raise RuntimeError("Not implemented")


def persist_notification(request_data: dict, service_id: str, status: str, status_reason: str):
    """
    Create a Notification instance, and persist it in the database.
    """

    raise RuntimeError("Not implemented")
    # TODO - query
