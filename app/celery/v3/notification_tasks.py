# TODO - Should I continue using this?  It has side-effects.
from app import notify_celery
from app.models import Service


@notify_celery.task
def v3_process_notification(request_data: dict, service: Service):
    """
    This is the first task used to process request data send to POST /v3/notification/(email|sms).  It performs
    additional, non-schema verifications that require database queries:
    
    1. The specified template exists is for the specified type of notification.
    2. ...etc...
    """

    raise RuntimeError("Not implemented")
