import pytest
from app.celery.v3.notification_tasks import v3_process_notification
from app.models import EMAIL_TYPE, KEY_TYPE_TEST, Notification, NOTIFICATION_PERMANENT_FAILURE, SMS_TYPE
from sqlalchemy import select
from uuid import uuid4


# TODO - Make the Notification.template_id field nullable?  Have a default template?
@pytest.mark.xfail(reason="A Notification with an invalid template ID cannot be persisted.")
def test_v3_process_notification_no_template(notify_db_session, sample_service):
    """
    Call the task with request data referencing a nonexistent template.
    """

    request_data = {
        "id": str(uuid4()),
        "notification_type": EMAIL_TYPE,
        "email_address": "test@va.gov",
        "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
    }

    v3_process_notification(
        request_data,
        sample_service.id,
        None,
        KEY_TYPE_TEST
    )

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.execute(query).one().Notification
    assert notification.status == NOTIFICATION_PERMANENT_FAILURE
    assert notification.status_reason == "The template does not exist."


@pytest.mark.xfail(reason="This test needs a template not owned by sample_service.", run=False)
def test_v3_process_notification_template_owner_mismatch(
    notify_db_session, sample_service, sample_template, sample_template_without_email_permission
):
    """
    Call the task with request data for a template the service doesn't own.
    """

    assert sample_template.template_type == SMS_TYPE
    assert sample_template.service_id == sample_service.id

    assert sample_template_without_email_permission.template_type == EMAIL_TYPE
    assert sample_template_without_email_permission.service_id != sample_service.id
    assert False

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": sample_template.id,
    }

    v3_process_notification(
        request_data,
        sample_service.id,
        None,
        KEY_TYPE_TEST
    )

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.execute(query).one().Notification
    assert notification.status == NOTIFICATION_PERMANENT_FAILURE
    assert notification.status_reason == "The service does not own the template."


def test_v3_process_notification_template_type_mismatch(notify_db_session, sample_service, sample_template):
    """
    Call the task with request data for an e-mail notification, but specify and SMS template.
    """

    assert sample_template.template_type == SMS_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": EMAIL_TYPE,
        "email_address": "test@va.gov",
        "template_id": sample_template.id,
    }

    v3_process_notification(
        request_data,
        sample_service.id,
        None,
        KEY_TYPE_TEST
    )

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.execute(query).one().Notification
    assert notification.status == NOTIFICATION_PERMANENT_FAILURE
    assert notification.status_reason == "The template type does not match the notification type."
