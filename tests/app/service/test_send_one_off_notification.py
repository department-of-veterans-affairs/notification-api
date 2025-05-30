import uuid
from unittest.mock import Mock

import pytest
from notifications_utils.recipients import InvalidPhoneError
from sqlalchemy import delete

from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    SMS_TYPE,
    Notification,
)
from app.service.send_notification import send_one_off_notification
from app.v2.errors import BadRequestError, TooManyRequestsError


@pytest.fixture
def persist_mock(mocker):
    noti = Mock(id=uuid.uuid4())
    return mocker.patch('app.service.send_notification.persist_notification', return_value=noti)


@pytest.fixture
def celery_mock(mocker):
    return mocker.patch('app.service.send_notification.send_notification_to_queue')


def test_send_one_off_notification_calls_celery_correctly(
    notify_db_session,
    sample_service,
    sample_template,
    persist_mock,
    celery_mock,
):
    service = sample_service()
    template = sample_template(service=service)

    service = template.service

    post_data = {'template_id': str(template.id), 'to': '6502532222', 'created_by': str(service.created_by_id)}

    resp = send_one_off_notification(service.id, post_data)

    assert resp == {'id': str(persist_mock.return_value.id)}

    celery_mock.assert_called_once_with(notification=persist_mock.return_value, research_mode=False)


def test_send_one_off_notification_calls_persist_correctly_for_sms(
    notify_db_session,
    persist_mock,
    sample_service,
    sample_template,
    celery_mock,
):
    service = sample_service()
    template = sample_template(
        service=service,
        content='Hello (( Name))\nYour thing is due soon',
    )

    post_data = {
        'template_id': str(template.id),
        'to': '6502532222',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        template_postage=None,
        recipient=post_data['to'],
        service_id=template.service.id,
        personalisation={'name': 'foo'},
        notification_type=SMS_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text='testing',
        reference=None,
    )


def test_send_one_off_notification_calls_persist_correctly_for_email(
    persist_mock, celery_mock, sample_service, sample_template, notify_db_session
):
    service = sample_service(email_address=None)
    template = sample_template(
        service=service,
        template_type=EMAIL_TYPE,
        subject='Test subject',
        content='Hello (( Name))\nYour thing is due soon',
    )

    post_data = {
        'template_id': str(template.id),
        'to': 'test@example.com',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        template_postage=None,
        recipient=post_data['to'],
        service_id=template.service.id,
        personalisation={'name': 'foo'},
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text=None,
        reference=None,
    )


def test_send_one_off_notification_honors_research_mode(
    notify_db_session,
    persist_mock,
    celery_mock,
    sample_service,
    sample_template,
):
    service = sample_service(research_mode=True)
    template = sample_template(service=service)

    post_data = {'template_id': str(template.id), 'to': '6502532222', 'created_by': str(service.created_by_id)}

    send_one_off_notification(service.id, post_data)

    assert celery_mock.call_args[1]['research_mode'] is True


def test_send_one_off_notification_raises_if_invalid_recipient(
    notify_db_session,
    sample_service,
    sample_template,
):
    service = sample_service()
    template = sample_template(service=service)

    post_data = {'template_id': str(template.id), 'to': 'not a phone number', 'created_by': str(service.created_by_id)}

    with pytest.raises(InvalidPhoneError):
        send_one_off_notification(service.id, post_data)


def test_send_one_off_notification_raises_if_over_limit(
    notify_db_session,
    mocker,
    sample_service,
    sample_template,
):
    service = sample_service(message_limit=0)
    template = sample_template(service=service)
    mocker.patch(
        'app.service.send_notification.check_service_over_daily_message_limit', side_effect=TooManyRequestsError(1)
    )

    post_data = {'template_id': str(template.id), 'to': '6502532222', 'created_by': str(service.created_by_id)}

    with pytest.raises(TooManyRequestsError):
        send_one_off_notification(service.id, post_data)


def test_send_one_off_notification_fails_if_created_by_other_service(sample_template, sample_user):
    user_not_in_service = sample_user(email='some-other-user@va.gov')
    template = sample_template()

    post_data = {'template_id': str(template.id), 'to': '6502532222', 'created_by': str(user_not_in_service.id)}

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(template.service_id, post_data)

    assert (
        e.value.message == f'Can’t create notification - Test User is not part of the "{template.service.name}" service'
    )


def test_send_one_off_sms_notification_should_use_sms_sender_reply_to_text(
    notify_db_session,
    sample_service,
    sample_sms_sender,
    sample_template,
    celery_mock,
):
    service = sample_service()
    template = sample_template(service=service)
    sms_sender = sample_sms_sender(service_id=service.id, sms_sender='6502532222', is_default=False)

    data = {
        'to': '6502532223',
        'template_id': str(template.id),
        'created_by': str(service.created_by_id),
        'sender_id': str(sms_sender.id),
    }

    notification_id: dict = send_one_off_notification(service_id=service.id, post_data=data)
    notification = notify_db_session.session.get(Notification, notification_id['id'])
    celery_mock.assert_called_once_with(notification=notification, research_mode=False)

    assert notification.reply_to_text == '+16502532222'

    # Teardown
    stmt = delete(Notification).where(Notification.id == notification_id['id'])
    notify_db_session.session.execute(stmt)
    notify_db_session.session.commit()


def test_send_one_off_sms_notification_should_use_default_service_reply_to_text(
    notify_db_session,
    sample_service,
    sample_sms_sender,
    sample_template,
    celery_mock,
):
    service = sample_service()
    template = sample_template(service=service)
    service.service_sms_senders[0].is_default = False
    sample_sms_sender(service_id=service.id, sms_sender='6502532222', is_default=True)

    data = {
        'to': '6502532223',
        'template_id': str(template.id),
        'created_by': str(service.created_by_id),
    }

    notification_id: dict = send_one_off_notification(service_id=service.id, post_data=data)
    notification = notify_db_session.session.get(Notification, notification_id['id'])
    celery_mock.assert_called_once_with(notification=notification, research_mode=False)

    assert notification.reply_to_text == '+16502532222'

    # Teardown
    stmt = delete(Notification).where(Notification.id == notification_id['id'])
    notify_db_session.session.execute(stmt)
    notify_db_session.session.commit()


def test_send_one_off_notification_should_throw_exception_if_reply_to_id_doesnot_exist(sample_template):
    tempplate = sample_template(template_type=EMAIL_TYPE)
    data = {
        'to': 'ok@ok.com',
        'template_id': str(tempplate.id),
        'sender_id': str(uuid.uuid4()),
        'created_by': str(tempplate.service.created_by_id),
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=tempplate.service.id, post_data=data)
    assert e.value.message == 'Reply to email address not found'


def test_send_one_off_notification_should_throw_exception_if_sms_sender_id_doesnot_exist(sample_template):
    template = sample_template()
    data = {
        'to': '6502532222',
        'template_id': str(template.id),
        'sender_id': str(uuid.uuid4()),
        'created_by': str(template.service.created_by_id),
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=template.service.id, post_data=data)
    assert e.value.message == 'SMS sender not found'
