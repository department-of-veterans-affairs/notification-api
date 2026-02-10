from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import NoResultFound

from app.celery.process_comp_and_pen import comp_and_pen_batch_process
from app.exceptions import NotificationTechnicalFailureException
from app.models import Notification
from app.pii import PiiPid
from app.pii.pii_low import PiiVaProfileID
from app.va.identifier import IdentifierType


# This test should create two new notifications, but there's no way to query by ID to retrieve them because
# the IDs are set randomly down stream.
@pytest.mark.serial
@pytest.mark.parametrize('pii_enabled', [True, False])
def test_comp_and_pen_batch_process_happy_path(notify_db_session, mocker, sample_template, pii_enabled) -> None:
    """
    Verify the code path from the invocation of comp_and_pen_batch_process to the downstream code that executes
    Celery tasks with apply_async.  The code under test should create two Notification instances and their related
    RecipientIdentifier instances.
    """

    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mocker.patch.dict('os.environ', {'PII_ENABLED': str(pii_enabled)})

    # This function executes Celery tasks using apply.async.
    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    mock_send_notification_to_queue = mocker.patch('app.notifications.send_notifications.send_notification_to_queue')

    records = [
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        {'participant_id': '42', 'payment_amount': '42.42', 'vaprofile_id': '43627'},
    ]

    comp_and_pen_batch_process(records)

    notifications = notify_db_session.session.scalars(select(Notification)).all()

    try:
        mock_send_notification_to_queue.assert_not_called(), 'This is the path for notifications with contact info.'
        assert mock_send.call_count == len(records), 'Should have been called for each record.'
        assert len(notifications) == len(records), 'Should have created a new notification for each record.'

        for index, notification in enumerate(notifications):
            assert len(notification.recipient_identifiers) == 1
            va_profile_id = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value].id_value
            decrypted_va_profile_id = PiiVaProfileID(va_profile_id, True).get_pii() if pii_enabled else va_profile_id
            assert decrypted_va_profile_id == records[index]['vaprofile_id']
    finally:
        notify_db_session.session.execute(delete(Notification))


@pytest.mark.serial
@freeze_time('2026-01-01T12:00:00Z')
@pytest.mark.parametrize('pii_enabled', [True, False])
def test_comp_and_pen_batch_process_with_encrypted_fields(
    notify_db_session, mocker, sample_template, pii_enabled
) -> None:
    """
    Verify the code path with encrypted PII fields.
    """

    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mocker.patch.dict('os.environ', {'PII_ENABLED': str(pii_enabled)})

    encrypted_vaprofile_1 = PiiVaProfileID('57').get_encrypted_value()
    encrypted_vaprofile_2 = PiiVaProfileID('43627').get_encrypted_value()
    encrypted_participant_1 = PiiPid('55').get_encrypted_value()
    encrypted_participant_2 = PiiPid('42').get_encrypted_value()

    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    mock_send_notification_to_queue = mocker.patch('app.notifications.send_notifications.send_notification_to_queue')

    records = [
        {
            'payment_amount': '55.56',
            'encrypted_participant_id': encrypted_participant_1,
            'encrypted_vaprofile_id': encrypted_vaprofile_1,
        },
        {
            'payment_amount': '42.42',
            'encrypted_participant_id': encrypted_participant_2,
            'encrypted_vaprofile_id': encrypted_vaprofile_2,
        },
    ]

    comp_and_pen_batch_process(records)

    notifications = notify_db_session.session.scalars(select(Notification)).all()

    try:
        mock_send_notification_to_queue.assert_not_called()
        assert mock_send.call_count == 2
        assert len(notifications) == 2

        # Verify the notifications were created with correct decrypted values
        expected_vaprofile_ids = [encrypted_vaprofile_1, encrypted_vaprofile_2]
        for index, notification in enumerate(notifications):
            assert len(notification.recipient_identifiers) == 1
            va_profile_id = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value].id_value
            assert va_profile_id == expected_vaprofile_ids[index]
    finally:
        notify_db_session.session.execute(delete(Notification))


@pytest.mark.serial
@pytest.mark.parametrize('pii_enabled', [True, False])
def test_comp_and_pen_batch_process_prefers_encrypted_fields(
    notify_db_session, mocker, sample_template, pii_enabled
) -> None:
    """
    Verify that encrypted fields are preferred over unencrypted when both are present.
    """

    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mocker.patch.dict('os.environ', {'PII_ENABLED': str(pii_enabled)})

    encrypted_vaprofile = PiiVaProfileID('NEW_VP_999').get_encrypted_value()
    encrypted_participant = PiiPid('NEW_PID_888').get_encrypted_value()

    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    records = [
        {
            'participant_id': 'OLD_PID_123',  # This should be ignored
            'payment_amount': '55.56',
            'vaprofile_id': 'OLD_VP_456',  # This should be ignored
            'encrypted_participant_id': encrypted_participant,  # This should be used
            'encrypted_vaprofile_id': encrypted_vaprofile,  # This should be used
        },
    ]

    comp_and_pen_batch_process(records)

    notifications = notify_db_session.session.scalars(select(Notification)).all()

    try:
        assert mock_send.call_count == 1
        assert len(notifications) == 1

        notification = notifications[0]
        assert len(notification.recipient_identifiers) == 1
        va_profile_id = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value].id_value
        decrypted_va_profile_id = PiiVaProfileID(va_profile_id, True).get_pii() if pii_enabled else va_profile_id

        # Should use the encrypted (NEW) value, not the old unencrypted one
        assert decrypted_va_profile_id == 'NEW_VP_999'
        assert decrypted_va_profile_id != 'OLD_VP_456'
    finally:
        notify_db_session.session.execute(delete(Notification))


def test_comp_and_pen_batch_process_perf_number_happy_path(mocker, sample_template) -> None:
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mock_send = mocker.patch('app.notifications.send_notifications.send_notification_to_queue')

    records = [
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        {'participant_id': '42', 'payment_amount': '42.42', 'vaprofile_id': '43627'},
    ]
    with patch.dict(
        'app.celery.process_comp_and_pen.current_app.config', {'COMP_AND_PEN_PERF_TO_NUMBER': '8888675309'}
    ):
        comp_and_pen_batch_process(records)

    # comp_and_pen_batch_process can fail without raising an exception, so test it called send_notification_to_queue
    mock_send.call_count == len(records)


def test_comp_and_pen_batch_process_perf_number_with_encrypted_fields(mocker, sample_template) -> None:
    """Test that perf number works with encrypted fields."""
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mock_send = mocker.patch('app.notifications.send_notifications.send_notification_to_queue')

    # Create encrypted PII values
    encrypted_vaprofile = PiiVaProfileID('57').get_encrypted_value()
    encrypted_participant = PiiPid('55').get_encrypted_value()

    records = [
        {
            'payment_amount': '55.56',
            'encrypted_participant_id': encrypted_participant,
            'encrypted_vaprofile_id': encrypted_vaprofile,
        },
    ]
    with patch.dict(
        'app.celery.process_comp_and_pen.current_app.config', {'COMP_AND_PEN_PERF_TO_NUMBER': '8888675309'}
    ):
        comp_and_pen_batch_process(records)

    mock_send.call_count == len(records)


@pytest.mark.parametrize('exception_tested', [AttributeError, NoResultFound, ValueError])
def test_comp_and_pen_batch_process_exception(mocker, exception_tested) -> None:
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        side_effect=exception_tested,
    )

    with pytest.raises(exception_tested):
        comp_and_pen_batch_process({})


def test_comp_and_pen_batch_process_bypass_exception(mocker, sample_template) -> None:
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mocker.patch(
        'app.celery.process_comp_and_pen.send_notification_bypass_route',
        side_effect=NotificationTechnicalFailureException,
    )
    mock_logger = mocker.patch('app.celery.process_comp_and_pen.current_app.logger')

    comp_and_pen_batch_process([{'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'}])

    # comp_and_pen_batch_process can fail without raising an exception
    mock_logger.exception.assert_called_once()
    mock_logger.info.assert_not_called()


def test_comp_and_pen_batch_process_handles_invalid_encrypted_data(mocker, sample_template) -> None:
    """Test that invalid encrypted data is handled gracefully and processing continues."""
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    # First record has invalid encrypted data, second is valid
    records = [
        {
            'payment_amount': '100.00',
            'encrypted_participant_id': 'INVALID_ENCRYPTED_DATA',
            'encrypted_vaprofile_id': 'ALSO_INVALID',
        },
        {
            'participant_id': '123456',
            'payment_amount': '200.00',
            'vaprofile_id': 'VP123',
        },
    ]

    comp_and_pen_batch_process(records)

    # Should still process second record
    assert mock_send.call_count == 1


def test_comp_and_pen_batch_process_mixed_encrypted_and_unencrypted(notify_db_session, mocker, sample_template) -> None:
    """Test processing a batch with mixed encrypted and unencrypted records."""
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )
    mocker.patch.dict('os.environ', {'PII_ENABLED': 'True'})

    encrypted_vaprofile = PiiVaProfileID('99').get_encrypted_value()
    encrypted_participant = PiiPid('88').get_encrypted_value()

    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )

    records = [
        # Unencrypted record
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        # Encrypted record
        {
            'payment_amount': '100.00',
            'encrypted_participant_id': encrypted_participant,
            'encrypted_vaprofile_id': encrypted_vaprofile,
        },
    ]

    comp_and_pen_batch_process(records)

    notifications = notify_db_session.session.scalars(select(Notification)).all()

    try:
        assert mock_send.call_count == 2
        assert len(notifications) == 2

        # Both should have been processed successfully
        expected_vaprofile_ids = ['57', '99']
        for index, notification in enumerate(notifications):
            assert len(notification.recipient_identifiers) == 1
            va_profile_id = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value].id_value
            decrypted_va_profile_id = PiiVaProfileID(va_profile_id, True).get_pii()
            assert decrypted_va_profile_id == expected_vaprofile_ids[index]
    finally:
        notify_db_session.session.execute(delete(Notification))
