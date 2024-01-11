import pytest
from app.dao.notifications_dao import (
    delete_notifications_older_than_retention_by_type,
    insert_update_notification_history,
)
from app.models import (
    Notification,
    NotificationHistory,
    RecipientIdentifier,
    EMAIL_TYPE,
    LETTER_TYPE,
    SMS_TYPE,
)
from app.notifications.process_notifications import persist_notification
from app.va.identifier import IdentifierType
from datetime import date, datetime, timedelta
from flask import current_app
from freezegun import freeze_time
from tests.app.db import create_service_data_retention


def create_test_data(
    notify_db_session, notification_type, sample_service, sample_template, sample_notification, days_of_retention=3
):
    service_with_default_data_retention = sample_service(service_name='default data retention')
    email_template, letter_template, sms_template = _create_templates(sample_service, sample_template)
    default_email_template, default_letter_template, default_sms_template = _create_templates(
        service_with_default_data_retention, sample_template
    )
    sample_notification(template=email_template, status='delivered')
    sample_notification(template=sms_template, status='permanent-failure')
    sample_notification(
        template=letter_template, status='temporary-failure', reference='LETTER_REF', sent_at=datetime.utcnow()
    )
    sample_notification(template=email_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=4))
    sample_notification(
        template=sms_template, status='permanent-failure', created_at=datetime.utcnow() - timedelta(days=4)
    )
    sample_notification(
        template=letter_template,
        status='temporary-failure',
        reference='LETTER_REF',
        sent_at=datetime.utcnow(),
        created_at=datetime.utcnow() - timedelta(days=4),
    )
    sample_notification(
        template=default_email_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=8)
    )
    sample_notification(
        template=default_sms_template, status='permanent-failure', created_at=datetime.utcnow() - timedelta(days=8)
    )
    sample_notification(
        template=default_letter_template,
        status='temporary-failure',
        reference='LETTER_REF',
        sent_at=datetime.utcnow(),
        created_at=datetime.utcnow() - timedelta(days=8),
    )

    sdr = create_service_data_retention(
        service=sample_service, notification_type=notification_type, days_of_retention=days_of_retention
    )

    yield

    # Teardown
    notify_db_session.session.delete(sdr)
    notify_db_session.session.commit()


def _create_templates(sample_service, sample_template):
    service = sample_service()
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    sms_template = sample_template(service=service)
    letter_template = sample_template(service=service, template_type=LETTER_TYPE)
    return email_template, letter_template, sms_template


@pytest.mark.parametrize(
    'month, delete_run_time',
    [
        (4, '2016-04-10 23:40'),
        (1, '2016-01-11 00:40'),
    ],
)
@pytest.mark.parametrize(
    'notification_type, expected_sms_count, expected_email_count, expected_letter_count',
    [
        (EMAIL_TYPE, 10, 7, 10),
        (LETTER_TYPE, 10, 10, 7),
        (SMS_TYPE, 7, 10, 10),
    ],
)
def test_should_delete_notifications_by_type_after_seven_days(
    mocker,
    sample_service,
    sample_template,
    sample_notification,
    month,
    delete_run_time,
    notification_type,
    expected_sms_count,
    expected_email_count,
    expected_letter_count,
):
    mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    email_template, letter_template, sms_template = _create_templates(sample_service, sample_template)

    # For each notification type, create one notification a day between the 1st and 10th from 11:00 to 19:00.
    for i in range(1, 11):
        past_date = '2016-0{0}-{1:02d}  {1:02d}:00:00.000000'.format(month, i)
        with freeze_time(past_date):
            sample_notification(template=email_template, created_at=datetime.utcnow(), status='permanent-failure')
            sample_notification(template=sms_template, created_at=datetime.utcnow(), status='delivered')
            sample_notification(template=letter_template, created_at=datetime.utcnow(), status='temporary-failure')
    assert Notification.query.count() == 30

    # Records from before the 3rd should be deleted.
    with freeze_time(delete_run_time):
        delete_notifications_older_than_retention_by_type(notification_type)

    remaining_sms_notifications = Notification.query.filter_by(notification_type=SMS_TYPE).all()
    remaining_letter_notifications = Notification.query.filter_by(notification_type=LETTER_TYPE).all()
    remaining_email_notifications = Notification.query.filter_by(notification_type=EMAIL_TYPE).all()
    assert len(remaining_sms_notifications) == expected_sms_count
    assert len(remaining_email_notifications) == expected_email_count
    assert len(remaining_letter_notifications) == expected_letter_count

    if notification_type == SMS_TYPE:
        notifications_to_check = remaining_sms_notifications
    elif notification_type == EMAIL_TYPE:
        notifications_to_check = remaining_email_notifications
    elif notification_type == LETTER_TYPE:
        notifications_to_check = remaining_letter_notifications

    for notification in notifications_to_check:
        assert notification.created_at.date() >= date(2016, month, 3)


@pytest.mark.parametrize(
    'month, delete_run_time',
    [
        (4, '2016-04-10 23:40'),
        (1, '2016-01-11 00:40'),
    ],
)
@pytest.mark.parametrize(
    'notification_type, expected_count',
    [
        (EMAIL_TYPE, 7),
        (SMS_TYPE, 7),
    ],
)
def test_should_delete_notification_and_recipient_identifiers_when_bulk_deleting(
    month,
    delete_run_time,
    notification_type,
    expected_count,
    sample_template,
    sample_api_key,
    mocker,
    notify_db_session,
):
    mocker.patch('app.notifications.process_notifications.accept_recipient_identifiers_enabled', return_value=True)

    api_key = sample_api_key()
    template = sample_template(template_type=notification_type)

    # Create one notification a day of each type between the 1st and 10th from 11:00 to 19:00.
    for i in range(1, 11):
        past_date = '2016-0{0}-{1:02d}  {1:02d}:00:00.000000'.format(month, i)
        with freeze_time(past_date):
            recipient_identifier = {'id_type': IdentifierType.VA_PROFILE_ID.value, 'id_value': 'foo'}
            notification = persist_notification(
                template_id=template.id,
                template_version=template.version,
                service_id=template.service.id,
                personalisation=None,
                notification_type=notification_type,
                api_key_id=api_key.id,
                key_type=api_key.key_type,
                recipient_identifier=recipient_identifier,
                created_at=datetime.utcnow(),
            )

    assert Notification.query.count() == 10
    assert RecipientIdentifier.query.count() == 10

    # Records from before 3rd should be deleted
    with freeze_time(delete_run_time):
        delete_notifications_older_than_retention_by_type(notification_type)

    try:
        remaining_notifications = Notification.query.filter_by(notification_type=notification_type).all()
        assert len(remaining_notifications) == expected_count

        remaining_recipient_identifiers = RecipientIdentifier.query.all()
        assert len(remaining_recipient_identifiers) == expected_count
    finally:
        # Teardown
        for notification in remaining_notifications:
            notify_db_session.session.delete(notification)
        for recipient_identifier in remaining_recipient_identifiers:
            notify_db_session.session.delete(recipient_identifier)
        notify_db_session.session.commit()


@freeze_time('2016-01-10 12:00:00.000000')
def test_should_not_delete_notification_history(sample_service, sample_template, sample_notification, mocker):
    mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    with freeze_time('2016-01-01 12:00'):
        email_template, letter_template, sms_template = _create_templates(sample_service, sample_template)
        sample_notification(template=email_template, status='permanent-failure')
        sample_notification(template=sms_template, status='permanent-failure')
        sample_notification(template=letter_template, status='permanent-failure')
    assert Notification.query.count() == 3
    delete_notifications_older_than_retention_by_type(SMS_TYPE)
    assert Notification.query.count() == 2
    assert NotificationHistory.query.count() == 1


@pytest.mark.parametrize('notification_type', [SMS_TYPE, EMAIL_TYPE, LETTER_TYPE])
def test_delete_notifications_for_days_of_retention(
    notify_db_session, sample_service, sample_template, sample_notification, notification_type, mocker
):
    mock_get_s3 = mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    create_test_data(notify_db_session, notification_type, sample_service, sample_template, sample_notification)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type(notification_type)
    assert Notification.query.count() == 7
    assert Notification.query.filter_by(notification_type=notification_type).count() == 1
    if notification_type == LETTER_TYPE:
        mock_get_s3.assert_called_with(
            bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
            subfolder='{}/NOTIFY.LETTER_REF.D.2.C.C'.format(str(datetime.utcnow().date())),
        )
        assert mock_get_s3.call_count == 2
    else:
        mock_get_s3.assert_not_called()


def test_delete_notifications_inserts_notification_history(
    notify_db_session, sample_service, sample_template, sample_notification
):
    create_test_data(notify_db_session, SMS_TYPE, sample_service, sample_template, sample_notification)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type(SMS_TYPE)
    assert Notification.query.count() == 7

    assert NotificationHistory.query.count() == 2


def test_delete_notifications_updates_notification_history(sample_template, sample_notification, mocker):
    mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    template = sample_template(template_type=EMAIL_TYPE)
    notification = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=8))
    Notification.query.filter_by(id=notification.id).update(
        {
            'status': 'delivered',
            'reference': 'ses_reference',
            'billable_units': 1,  # I know we don't update this for emails but this is a unit test
            'updated_at': datetime.utcnow(),
            'sent_at': datetime.utcnow(),
            'sent_by': 'ses',
        }
    )

    delete_notifications_older_than_retention_by_type(EMAIL_TYPE)

    history = NotificationHistory.query.all()
    assert len(history) == 1
    assert history[0].status == 'delivered'
    assert history[0].reference == 'ses_reference'
    assert history[0].billable_units == 1
    assert history[0].updated_at
    assert history[0].sent_by == 'ses'


def test_delete_notifications_keep_data_for_days_of_retention_is_longer(
    notify_db_session, sample_service, sample_template, sample_notification
):
    create_test_data(notify_db_session, SMS_TYPE, sample_service, sample_template, sample_notification, 15)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type(SMS_TYPE)
    assert Notification.query.count() == 8
    assert Notification.query.filter(Notification.notification_type == SMS_TYPE).count() == 2


def test_delete_notifications_with_test_keys(sample_template, sample_notification, mocker):
    mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    sample_notification(template=sample_template(), key_type='test', created_at=datetime.utcnow() - timedelta(days=8))
    delete_notifications_older_than_retention_by_type(SMS_TYPE)
    assert Notification.query.count() == 0


def test_delete_notifications_delete_notification_type_for_default_time_if_no_days_of_retention_for_type(
    sample_service, sample_template, sample_notification
):
    email_template, letter_template, sms_template = _create_templates(sample_service, sample_template)

    # Retention should apply to the service associated with the above templates.
    assert email_template.service.id == letter_template.service.id
    assert sms_template.service.id == letter_template.service.id
    create_service_data_retention(service=email_template.service, notification_type=SMS_TYPE, days_of_retention=15)

    sample_notification(template=email_template, status='delivered')
    sample_notification(template=sms_template, status='permanent-failure')
    sample_notification(template=letter_template, status='temporary-failure')
    sample_notification(template=email_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=14))
    sample_notification(
        template=sms_template, status='permanent-failure', created_at=datetime.utcnow() - timedelta(days=14)
    )
    sample_notification(
        template=letter_template, status='temporary-failure', created_at=datetime.utcnow() - timedelta(days=14)
    )
    assert Notification.query.count() == 6
    delete_notifications_older_than_retention_by_type(EMAIL_TYPE)
    assert Notification.query.count() == 5
    assert Notification.query.filter_by(notification_type=EMAIL_TYPE).count() == 1


def test_delete_notifications_does_try_to_delete_from_s3_when_letter_has_not_been_sent(
    mocker, sample_template, sample_notification
):
    mock_get_s3 = mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    letter_template = sample_template(template_type=LETTER_TYPE)

    sample_notification(template=letter_template, status='sending', reference='LETTER_REF')
    delete_notifications_older_than_retention_by_type(EMAIL_TYPE, qry_limit=1)
    mock_get_s3.assert_not_called()


@freeze_time('2016-01-10 12:00:00.000000')
def test_should_not_delete_notification_if_history_does_not_exist(
    mocker, sample_service, sample_template, sample_notification
):
    mocker.patch('app.dao.notifications_dao.get_s3_bucket_objects')
    mocker.patch('app.dao.notifications_dao.insert_update_notification_history')
    with freeze_time('2016-01-01 12:00'):
        email_template, letter_template, sms_template = _create_templates(sample_service, sample_template)
        sample_notification(template=email_template, status='permanent-failure')
        sample_notification(template=sms_template, status='delivered')
        sample_notification(template=letter_template, status='temporary-failure')
    assert Notification.query.count() == 3
    delete_notifications_older_than_retention_by_type(SMS_TYPE)
    assert Notification.query.count() == 3
    assert NotificationHistory.query.count() == 0


def test_delete_notifications_calls_subquery_multiple_times(sample_template, sample_notification):
    template = sample_template()
    sample_notification(template=template, created_at=datetime.now() - timedelta(days=8))
    sample_notification(template=template, created_at=datetime.now() - timedelta(days=8))
    sample_notification(template=template, created_at=datetime.now() - timedelta(days=8))

    assert Notification.query.count() == 3
    delete_notifications_older_than_retention_by_type(SMS_TYPE, qry_limit=1)
    assert Notification.query.count() == 0


def test_delete_notifications_returns_sum_correctly(sample_service, sample_template, sample_notification):
    template = sample_template()
    sample_notification(template=template, created_at=datetime.now() - timedelta(days=8))
    sample_notification(template=template, created_at=datetime.now() - timedelta(days=8))

    s2 = sample_service(service_name='s2')
    t2 = sample_template(service=s2, template_type=SMS_TYPE)
    assert template.service.id != t2.service.id
    sample_notification(template=t2, created_at=datetime.now() - timedelta(days=8))
    sample_notification(template=t2, created_at=datetime.now() - timedelta(days=8))

    ret = delete_notifications_older_than_retention_by_type(SMS_TYPE, qry_limit=1)
    assert ret == 4


def test_insert_update_notification_history(sample_service, sample_template, sample_notification):
    service = sample_service()
    template = sample_template(service=service, template_type=SMS_TYPE)
    notification_1 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=3))
    notification_2 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=8))
    notification_3 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=9))
    other_types = [EMAIL_TYPE, LETTER_TYPE]
    for template_type in other_types:
        t = sample_template(service=service, template_type=template_type)
        sample_notification(template=t, created_at=datetime.utcnow() - timedelta(days=3))
        sample_notification(template=t, created_at=datetime.utcnow() - timedelta(days=8))

    insert_update_notification_history(
        notification_type=SMS_TYPE, date_to_delete_from=datetime.utcnow() - timedelta(days=7), service_id=service.id
    )
    history = NotificationHistory.query.all()
    assert len(history) == 2

    history_ids = [x.id for x in history]
    assert notification_1.id not in history_ids
    assert notification_2.id in history_ids
    assert notification_3.id in history_ids


def test_insert_update_notification_history_only_insert_update_given_service(
    sample_service, sample_template, sample_notification
):
    template = sample_template()
    other_template = sample_template()
    assert template.service.id != other_template.service.id
    notification_1 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=3))
    notification_2 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=8))
    notification_3 = sample_notification(template=other_template, created_at=datetime.utcnow() - timedelta(days=3))
    notification_4 = sample_notification(template=other_template, created_at=datetime.utcnow() - timedelta(days=8))

    insert_update_notification_history(SMS_TYPE, datetime.utcnow() - timedelta(days=7), template.service.id)
    history = NotificationHistory.query.all()
    assert len(history) == 1

    history_ids = [x.id for x in history]
    assert notification_1.id not in history_ids
    assert notification_2.id in history_ids
    assert notification_3.id not in history_ids
    assert notification_4.id not in history_ids


def test_insert_update_notification_history_updates_history_with_new_status(sample_template, sample_notification):
    template = sample_template()
    notification_1 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=3))
    notification_2 = sample_notification(
        template=template, created_at=datetime.utcnow() - timedelta(days=8), status='delivered'
    )
    insert_update_notification_history(SMS_TYPE, datetime.utcnow() - timedelta(days=7), template.service_id)
    history = NotificationHistory.query.get(notification_2.id)
    assert history.status == 'delivered'
    assert not NotificationHistory.query.get(notification_1.id)


def test_insert_update_notification_history_updates_history_with_billing_code(sample_template, sample_notification):
    template = sample_template()
    notification_1 = sample_notification(template=template, created_at=datetime.utcnow() - timedelta(days=3))
    notification_2 = sample_notification(
        template=template, created_at=datetime.utcnow() - timedelta(days=8), billing_code='TESTCODE'
    )
    insert_update_notification_history(SMS_TYPE, datetime.utcnow() - timedelta(days=7), template.service_id)
    history = NotificationHistory.query.get(notification_2.id)
    assert history.billing_code == 'TESTCODE'
    assert not NotificationHistory.query.get(notification_1.id)
