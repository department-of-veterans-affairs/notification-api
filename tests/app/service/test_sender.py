import pytest

from flask import current_app
from sqlalchemy import select, or_

from app.dao.services_dao import dao_add_user_to_service
from app.models import Notification, EMAIL_TYPE, SMS_TYPE
from app.service.sender import send_notification_to_service_users


@pytest.mark.parametrize('notification_type', [
    EMAIL_TYPE,
    SMS_TYPE
])
def test_send_notification_to_service_users_persists_notifications_correctly(
    notify_db,
    notify_db_session,
    notification_type,
    sample_notify_service_user_session,
    sample_service,
    sample_template,
    mocker
):
    service = sample_service()
    user = service.users[0]

    mocker.patch('app.service.sender.send_notification_to_queue')

    notify_service, _ = sample_notify_service_user_session()
    template = sample_template(service=service, user=user, template_type=notification_type)
    send_notification_to_service_users(service_id=service.id, template_id=template.id)
    to = user.email_address if notification_type == EMAIL_TYPE else user.mobile_number

    # Complicated query required due to multicore
    stmt = select(Notification).where(Notification.service_id == notify_service.id)\
                               .where(Notification.to == to)
    notifications = notify_db_session.session.scalars(stmt).all()
    notification = notifications[0]

    assert len(notifications) == 1
    assert notification.to == to
    assert str(notification.service_id) == current_app.config['NOTIFY_SERVICE_ID']
    assert notification.template.id == template.id
    assert notification.template.template_type == notification_type
    assert notification.notification_type == notification_type
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()

    # Teardown
    notify_db_session.session.delete(notification)
    notify_db_session.session.commit()


def test_send_notification_to_service_users_sends_to_queue(
    notify_db,
    notify_db_session,
    sample_notify_service_user_session,
    sample_service,
    sample_template,
    mocker
):
    send_mock = mocker.patch('app.service.sender.send_notification_to_queue')

    service = sample_service()
    notify_service, _ = sample_notify_service_user_session()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(service_id=service.id, template_id=template.id)

    assert send_mock.called
    assert send_mock.call_count == 1

    # Teardown
    stmt = select(Notification).where(Notification.service_id == notify_service.id)
    for notification in notify_db_session.session.scalars(stmt).all():
        notify_db_session.session.delete(notification)
    notify_db_session.session.commit()


def test_send_notification_to_service_users_includes_user_fields_in_personalisation(
    notify_db,
    notify_db_session,
    sample_notify_service_user_session,
    sample_service,
    sample_template,
    mocker
):
    persist_mock = mocker.patch('app.service.sender.persist_notification')
    mocker.patch('app.service.sender.send_notification_to_queue')

    service = sample_service()
    notify_service, _ = sample_notify_service_user_session()
    user = service.users[0]

    template = sample_template(service=service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(
        service_id=service.id,
        template_id=template.id,
        include_user_fields=['name', 'email_address', 'state']
    )

    persist_call = persist_mock.call_args_list[0][1]

    assert len(persist_mock.call_args_list) == 1
    assert persist_call['personalisation'] == {
        'name': user.name,
        'email_address': user.email_address,
        'state': user.state,
    }

    # Teardown
    stmt = select(Notification).where(Notification.service_id == notify_service.id)
    for notification in notify_db_session.session.scalars(stmt).all():
        notify_db_session.session.delete(notification)
    notify_db_session.session.commit()


def test_send_notification_to_service_users_sends_to_active_users_only(
    notify_db,
    notify_db_session,
    sample_notify_service_user_session,
    sample_service,
    sample_template,
    sample_user,
    mocker
):
    mocker.patch('app.service.sender.send_notification_to_queue')

    notify_service, _ = sample_notify_service_user_session()

    first_active_user = sample_user()
    second_active_user = sample_user()
    pending_user = sample_user(state='pending')
    service = sample_service(user=first_active_user)
    dao_add_user_to_service(service, second_active_user)
    dao_add_user_to_service(service, pending_user)
    template = sample_template(service=service, template_type=EMAIL_TYPE)

    send_notification_to_service_users(service_id=service.id, template_id=template.id)

    # Complicated query required due to multicore
    stmt = select(Notification).where(Notification.service_id == notify_service.id)\
                               .where(or_(Notification.to == first_active_user.email_address,
                                          Notification.to == second_active_user.email_address,
                                          Notification.to == pending_user.email_address,
                                          ))

    notifications = notify_db_session.session.scalars(stmt).all()
    notifications_recipients = [notification.to for notification in notifications]

    assert len(notifications) == 2
    assert pending_user.email_address not in notifications_recipients
    assert first_active_user.email_address in notifications_recipients
    assert second_active_user.email_address in notifications_recipients

    # Teardown
    for notification in notifications:
        notify_db_session.session.delete(notification)
    notify_db_session.session.commit()
