import pytest
from app.celery.v3.notification_tasks import (
    v3_process_notification,
    v3_send_email_notification,
    v3_send_sms_notification,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    Notification,
    NOTIFICATION_CREATED,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENT,
    SMS_TYPE,
)
from sqlalchemy import select
from uuid import uuid4


############################################################################################
# Test non-schema validations.
############################################################################################

# TODO - Make the Notification.template_id field nullable?  Have a default template?
@pytest.mark.xfail(reason="A Notification with an invalid template ID cannot be persisted.")
def test_v3_process_notification_no_template(notify_db_session, mocker, sample_service):
    """
    Call the task with request data referencing a nonexistent template.
    """

    request_data = {
        "id": str(uuid4()),
        "notification_type": EMAIL_TYPE,
        "email_address": "test@va.gov",
        "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
    }

    v3_send_email_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_email_notification.delay")
    v3_process_notification(request_data, sample_service.id, None, KEY_TYPE_TEST)
    v3_send_email_notification_mock.assert_not_called()

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.scalar(query)
    assert notification.status == NOTIFICATION_PERMANENT_FAILURE
    assert notification.status_reason == "The template does not exist."


def test_v3_process_notification_template_owner_mismatch(
    notify_db_session, mocker, sample_service, sample_template
):
    """
    Call the task with request data for a template the service doesn't own.
    """

    service1 = sample_service()
    service2 = sample_service()
    assert service1.id != service2.id
    template = sample_template(service=service2)
    assert template.template_type == SMS_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": template.id,
    }

    v3_send_sms_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_sms_notification.delay")
    v3_process_notification(request_data, service1.id, None, KEY_TYPE_TEST)
    v3_send_sms_notification_mock.assert_not_called()

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.scalar(query)

    try:
        assert notification.status == NOTIFICATION_PERMANENT_FAILURE
        assert notification.status_reason == "The service does not own the template."
    finally:
        notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


def test_v3_process_notification_template_type_mismatch_1(notify_db_session, mocker, sample_service, sample_template):
    """
    Call the task with request data for an e-mail notification, but specify an SMS template.
    """

    service = sample_service()
    template = sample_template(service=service)
    assert template.template_type == SMS_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": EMAIL_TYPE,
        "email_address": "test@va.gov",
        "template_id": template.id,
    }

    v3_send_email_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_email_notification.delay")
    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)
    v3_send_email_notification_mock.assert_not_called()

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.scalar(query)

    try:
        assert notification.status == NOTIFICATION_PERMANENT_FAILURE
        assert notification.status_reason == "The template type does not match the notification type."
    finally:
        notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


def test_v3_process_notification_template_type_mismatch_2(
    notify_db_session, mocker, sample_service, sample_template
):
    """
    Call the task with request data for an SMS notification, but specify an e-mail template.
    """

    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    assert template.template_type == EMAIL_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": template.id,
    }

    v3_send_sms_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_sms_notification.delay")
    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)
    v3_send_sms_notification_mock.assert_not_called()

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.scalar(query)

    try:
        assert notification.status == NOTIFICATION_PERMANENT_FAILURE
        assert notification.status_reason == "The template type does not match the notification type."
    finally:
        notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


############################################################################################
# Test sending e-mail notifications.
############################################################################################

def test_v3_process_notification_valid_email(notify_db_session, mocker, sample_service, sample_template):
    """
    Given data for a valid e-mail notification, the task v3_process_notification should pass a Notification
    instance to the task v3_send_email_notification.
    """

    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    assert template.template_type == EMAIL_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": EMAIL_TYPE,
        "email_address": "test@va.gov",
        "template_id": template.id,
    }

    v3_send_email_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_email_notification.delay")
    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)
    v3_send_email_notification_mock.assert_called_once()
    assert isinstance(v3_send_email_notification_mock.call_args.args[0], Notification)


def test_v3_send_email_notification(mocker, sample_template, sample_notification):
    template = sample_template(template_type=EMAIL_TYPE)
    notification = sample_notification(template=template)
    assert notification.notification_type == EMAIL_TYPE
    assert notification.status == NOTIFICATION_CREATED

    client_mock = mocker.Mock()
    client_mock.send_email = mocker.Mock(return_value="provider reference")
    client_mock.get_name = mocker.Mock(return_value="client name")
    mocker.patch("app.celery.v3.notification_tasks.clients.get_email_client", return_value=client_mock)

    v3_send_email_notification(notification, template)

    client_mock.send_email.assert_called_once()
    assert notification.status == NOTIFICATION_SENT
    assert notification.reference == "provider reference"
    assert notification.sent_by == "client name"


############################################################################################
# Test sending SMS notifications.
############################################################################################

def test_v3_process_notification_valid_sms_with_sender_id(
    notify_db_session, mocker, sample_service, sample_template, sample_sms_sender
):
    """
    Given data for a valid SMS notification that includes an sms_sender_id, the task v3_process_notification
    should pass a Notification instance to the task v3_send_sms_notification.
    """

    service = sample_service()
    template = sample_template(service=service)
    assert template.template_type == SMS_TYPE
    sms_sender = sample_sms_sender(service.id)

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": template.id,
        "sms_sender_id": sms_sender.id,
    }

    v3_send_sms_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_sms_notification.delay")
    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)
    v3_send_sms_notification_mock.assert_called_once_with(
        mocker.ANY,
        sms_sender.sms_sender
    )
    assert isinstance(v3_send_sms_notification_mock.call_args.args[0], Notification)


def test_v3_process_notification_valid_sms_without_sender_id(
    notify_db_session, mocker, sample_service, sample_template, sample_sms_sender
):
    """
    Given data for a valid SMS notification that does not include an sms_sender_id, the task v3_process_notification
    should pass a Notification instance to the task v3_send_sms_notification.
    """

    service = sample_service()
    template = sample_template(service=service)
    assert template.template_type == SMS_TYPE
    sms_sender = sample_sms_sender(service.id)

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": template.id,
    }

    v3_send_sms_notification_mock = mocker.patch(
        "app.celery.v3.notification_tasks.v3_send_sms_notification.delay"
    )

    get_default_sms_sender_id_mock = mocker.patch(
        "app.celery.v3.notification_tasks.get_default_sms_sender_id",
        return_value=(None, sms_sender.id)
    )

    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)

    v3_send_sms_notification_mock.assert_called_once_with(
        mocker.ANY,
        sms_sender.sms_sender
    )

    _notification = v3_send_sms_notification_mock.call_args.args[0]
    assert isinstance(_notification, Notification)
    _err, _sender_id = get_default_sms_sender_id_mock.return_value
    assert _err is None
    assert _notification.sms_sender_id == _sender_id

    get_default_sms_sender_id_mock.assert_called_once_with(service.id)


def test_v3_process_notification_valid_sms_with_invalid_sender_id(
    notify_db_session, mocker, sample_service, sample_template, sample_sms_sender
):
    """
    Given data for a valid SMS notification that includes an INVALID sms_sender_id,
    v3_process_notification should NOT call v3_send_sms_notification after checking sms_sender_id.
    """

    service = sample_service()
    template = sample_template(service=service)
    assert template.template_type == SMS_TYPE

    request_data = {
        "id": str(uuid4()),
        "notification_type": SMS_TYPE,
        "phone_number": "+18006982411",
        "template_id": template.id,
        "sms_sender_id": '111a1111-aaaa-1aa1-aa11-a1111aa1a1a1',
    }

    v3_send_sms_notification_mock = mocker.patch("app.celery.v3.notification_tasks.v3_send_sms_notification.delay")
    v3_process_notification(request_data, service.id, None, KEY_TYPE_TEST)
    v3_send_sms_notification_mock.assert_not_called()

    query = select(Notification).where(Notification.id == request_data["id"])
    notification = notify_db_session.session.scalar(query)
    assert notification is not None

    try:
        assert notification.status == NOTIFICATION_PERMANENT_FAILURE
        assert notification.status_reason == "SMS sender 111a1111-aaaa-1aa1-aa11-a1111aa1a1a1 does not exist."
    finally:
        notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


def test_v3_send_sms_notification(mocker, sample_service, sample_template, sample_notification, sample_sms_sender):
    service = sample_service()
    template = sample_template()
    assert template.template_type == SMS_TYPE
    sms_sender = sample_sms_sender(service.id)
    notification = sample_notification(template=template)
    assert notification.notification_type == SMS_TYPE
    assert notification.status == NOTIFICATION_CREATED

    client_mock = mocker.Mock()
    client_mock.send_sms = mocker.Mock(return_value="provider reference")
    client_mock.get_name = mocker.Mock(return_value="client name")
    mocker.patch("app.celery.v3.notification_tasks.clients.get_sms_client", return_value=client_mock)

    v3_send_sms_notification(notification, sms_sender.sms_sender)
    client_mock.send_sms.assert_called_once_with(
        notification.to,
        notification.content,
        notification.client_reference,
        True,
        sms_sender.sms_sender
    )

    assert notification.status == NOTIFICATION_SENT
    assert notification.reference == "provider reference"
    assert notification.sent_by == "client name"
