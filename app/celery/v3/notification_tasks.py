# TODO - Should I continue using notify_celery?  It has side-effects.
from app import db, notify_celery
from app.dao.dao_utils import get_reader_session
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, Notification, NOTIFICATION_PERMANENT_FAILURE, SMS_TYPE, Template
from app.service.service_data import ServiceData
from datetime import datetime
from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound


@notify_celery.task
def v3_process_notification(request_data: dict, service_data: ServiceData):
    """
    This is the first task used to process request data send to POST /v3/notification/(email|sms).  It performs
    additional, non-schema verifications that require database queries:

    1. The specified template exists and is for the specified type of notification.
    2. The given service owns the specified template.
    x. ...etc...
    """

    notification = Notification(
        id=request_data["id"],
        to=request_data.get("email_address" if request_data["notification_type"] == EMAIL_TYPE else "phone_number"),
        service_id=service_data.id,
        template_id=request_data["template_id"],
        template_version=0,
        # TODO - v2 uses the imported value "api_user" for the api_key.
        # Does the list service_data.api_keys ever have more than one element?
        api_key_id=service_data.api_keys[0].id if service_data.api_keys else None,
        key_type=service_data.api_keys[0].key_type if service_data.api_keys else KEY_TYPE_NORMAL,
        notification_type=request_data["notification_type"],
        created_at=datetime.utcnow(),
        status=NOTIFICATION_PERMANENT_FAILURE,
        client_reference=request_data.get("client_reference"),
        reference=request_data.get("reference"),
        personalisation=request_data.get("personalisation"),
        sms_sender_id=request_data.get("sms_sender_id"),
        billing_code=request_data.get("billing_code")
    )

    # TODO - Catch db connection errors and retry?
    query = select(Template).where(Template.id == request_data["template_id"])
    with get_reader_session() as reader_session:
        try:
            template = reader_session.execute(query).one().Template
        except (MultipleResultsFound, NoResultFound):
            notification.status_reason = "The template does not exist."
            # TODO - This isn't an option right now because Notification.template_id is non-nullable and
            # must reference a valid template.
            # db.session.add(notification)
            # db.session.commit()
            # TODO - Delete logging when the above issue is remedied.
            current_app.logger.error(
                "Notification %s specified nonexistent template %s.", notification.id, notification.template_id
            )
            return

    notification.template_version = template.version
    if notification.notification_type == SMS_TYPE and notification.sms_sender_id is None:
        # Get the template or service default sms_sender_id.
        # TODO
        pass

    if service_data.id != template.service_id:
        notification.status_reason = "The service does not own the template."
        db.session.add(notification)
        db.session.commit()
        return

    if request_data["notification_type"] != template.template_type:
        notification.status_reason = "The template type does not match the notification type."
        db.session.add(notification)
        db.session.commit()
        return

    # Create the notification content using the template and personalization data.
    # TODO

    # Determine the provider.
    # Launch a new task to make an API call to the provider.
    print("MADE IT HERE 4")  # TODO
    raise NotImplementedError
