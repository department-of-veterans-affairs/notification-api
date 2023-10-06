# TODO - Should I continue using notify_celery?  It has side-effects.
from app import db, notify_celery
from app.dao.dao_utils import get_reader_session
from app.models import (
    EMAIL_TYPE,
    Notification,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_TECHNICAL_FAILURE,
    SMS_TYPE,
    Template,
)
from celery.utils.log import get_task_logger
from datetime import datetime
from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

logger = get_task_logger(__name__)


@notify_celery.task
def v3_process_notification(request_data: dict, service_id: str, api_key_id: str, api_key_type: str):
    """
    This is the first task used to process request data send to POST /v3/notification/(email|sms).  It performs
    additional, non-schema verifications that require database queries:

    1. The specified template exists.
    2. The specified template is for the specified type of notification.
    3. The given service owns the specified template.
    """

    current_app.logger.info("MADE IT HERE 2 app logger")  # TODO
    logger.info("MADE IT HERE 2 logger")  # TODO
    print("MADE IT HERE 2")  # TODO
    notification = Notification(
        id=request_data["id"],
        to=request_data.get("email_address" if request_data["notification_type"] == EMAIL_TYPE else "phone_number"),
        service_id=service_id,
        template_id=request_data["template_id"],
        template_version=0,
        api_key_id=api_key_id,
        key_type=api_key_type,
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
    if service_id != template.service_id:
        notification.status_reason = "The service does not own the template."
        db.session.add(notification)
        db.session.commit()
        return

    if request_data["notification_type"] != template.template_type:
        notification.status_reason = "The template type does not match the notification type."
        db.session.add(notification)
        db.session.commit()
        return

    if notification.to is None:
        # Launch a new task to get the contact information from VA Profile using the recipient ID.
        # TODO
        notification.status = NOTIFICATION_TECHNICAL_FAILURE
        notification.status_reason = "Sending with recipient_identifer is not yet implemented."
        db.session.add(notification)
        db.session.commit()
        return

    print("MADE IT HERE 3")  # TODO
    if notification.notification_type == EMAIL_TYPE:
        # TODO - Determine the provider.  For now, assume SES.
        v3_send_email_notification_with_ses.delay(notification)
    elif notification.notification_type == SMS_TYPE:
        if notification.sms_sender_id is None:
            # Get the template or service default sms_sender_id.
            # TODO
            notification.status = NOTIFICATION_TECHNICAL_FAILURE
            notification.status_reason = "Default logic for sms_sender_id is not yet implemented."
            db.session.add(notification)
            db.session.commit()
            return

        # TODO - Determine the provider.  For now, assume Pinpoint.
        print("MADE IT HERE 4")  # TODO
        v3_send_sms_notification_with_pinpoint.delay(notification)


@notify_celery.task(serializer="pickle")
def v3_send_email_notification_with_ses(notification: Notification):
    print("MADE IT HERE E-MAIL SES")


@notify_celery.task(serializer="pickle")
def v3_send_sms_notification_with_pinpoint(notification: Notification):
    print("MADE IT HERE SMS PINPOINT")
