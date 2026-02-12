from unittest.mock import patch

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import NoResultFound

from app.celery.process_comp_and_pen import (
    DynamoRecord,
    _resolve_pii_for_comp_and_pen,
    comp_and_pen_batch_process,
)
from app.exceptions import NotificationTechnicalFailureException
from app.models import Notification
from app.pii import Pii, PiiPid, PiiVaProfileID
from app.va.identifier import IdentifierType


class TestResolvePiiForCompAndPen:
    """Tests for the 4-scenario PII resolution logic."""

    def test_pii_enabled_ff_on_encrypted_fields(self, mocker):
        """PII_ENABLED FF ON + encrypted fields → Pii objects with is_encrypted=True."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=True)
        mock_pii_pid = mocker.patch('app.celery.process_comp_and_pen.PiiPid')
        mock_pii_va = mocker.patch('app.celery.process_comp_and_pen.PiiVaProfileID')

        item = DynamoRecord(
            payment_amount='10.00',
            encrypted_participant_id='enc_pid',
            encrypted_vaprofile_id='enc_va',
        )

        _resolve_pii_for_comp_and_pen(item)

        mock_pii_pid.assert_called_once_with('enc_pid', is_encrypted=True)
        mock_pii_va.assert_called_once_with('enc_va', is_encrypted=True)

    def test_pii_enabled_ff_prefers_encrypted_over_unencrypted(self, mocker):
        """When both encrypted and unencrypted fields are present, encrypted is preferred."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=True)
        mock_pii_pid = mocker.patch('app.celery.process_comp_and_pen.PiiPid')
        mock_pii_va = mocker.patch('app.celery.process_comp_and_pen.PiiVaProfileID')

        item = DynamoRecord(
            payment_amount='10.00',
            participant_id='plain_pid',
            vaprofile_id='plain_va',
            encrypted_participant_id='enc_pid',
            encrypted_vaprofile_id='enc_va',
        )

        _resolve_pii_for_comp_and_pen(item)

        mock_pii_pid.assert_called_once_with('enc_pid', is_encrypted=True)
        mock_pii_va.assert_called_once_with('enc_va', is_encrypted=True)

    def test_pii_enabled_ff_off_encrypted_fields(self, mocker):
        """PII_ENABLED FF OFF + encrypted fields → decrypt to plain strings."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=False)

        mock_pid_instance = mocker.MagicMock()
        mock_pid_instance.get_pii.return_value = 'decrypted_pid'
        mock_pii_pid = mocker.patch('app.celery.process_comp_and_pen.PiiPid', return_value=mock_pid_instance)

        mock_va_instance = mocker.MagicMock()
        mock_va_instance.get_pii.return_value = 'decrypted_va'
        mock_pii_va = mocker.patch('app.celery.process_comp_and_pen.PiiVaProfileID', return_value=mock_va_instance)

        item = DynamoRecord(
            payment_amount='10.00',
            encrypted_participant_id='enc_pid',
            encrypted_vaprofile_id='enc_va',
        )

        resolved_pid, resolved_va = _resolve_pii_for_comp_and_pen(item)

        mock_pii_pid.assert_called_once_with('enc_pid', is_encrypted=True)
        mock_pii_va.assert_called_once_with('enc_va', is_encrypted=True)
        assert resolved_pid == 'decrypted_pid'
        assert resolved_va == 'decrypted_va'

    def test_pii_enabled_ff_on_unencrypted_fields(self, mocker):
        """PII_ENABLED FF ON + unencrypted fields → encrypt by wrapping in Pii."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=True)
        mock_pii_pid = mocker.patch('app.celery.process_comp_and_pen.PiiPid')
        mock_pii_va = mocker.patch('app.celery.process_comp_and_pen.PiiVaProfileID')

        item = DynamoRecord(
            payment_amount='10.00',
            participant_id='plain_pid',
            vaprofile_id='plain_va',
        )

        _resolve_pii_for_comp_and_pen(item)

        mock_pii_pid.assert_called_once_with('plain_pid')
        mock_pii_va.assert_called_once_with('plain_va')

    def test_pii_enabled_ff_off_unencrypted_fields(self, mocker):
        """PII_ENABLED FF OFF + unencrypted fields → plain strings as-is."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=False)

        item = DynamoRecord(
            payment_amount='10.00',
            participant_id='plain_pid',
            vaprofile_id='plain_va',
        )

        resolved_pid, resolved_va = _resolve_pii_for_comp_and_pen(item)

        assert resolved_pid == 'plain_pid'
        assert resolved_va == 'plain_va'
        assert not isinstance(resolved_pid, Pii)
        assert not isinstance(resolved_va, Pii)

    def test_missing_fields_raises_value_error(self, mocker):
        """When neither encrypted nor unencrypted fields are present, raises ValueError."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=False)

        item = DynamoRecord(payment_amount='10.00')

        with pytest.raises(ValueError, match='missing required'):
            _resolve_pii_for_comp_and_pen(item)

    def test_decryption_failure_raises(self, mocker):
        """When decryption fails, the error should propagate."""
        mocker.patch('app.celery.process_comp_and_pen.is_feature_enabled', return_value=False)
        mocker.patch(
            'app.celery.process_comp_and_pen.PiiPid',
            side_effect=Exception('Decryption failed'),
        )

        item = DynamoRecord(
            payment_amount='10.00',
            encrypted_participant_id='bad_encrypted_data',
            encrypted_vaprofile_id='enc_va',
        )

        with pytest.raises(Exception, match='Decryption failed'):
            _resolve_pii_for_comp_and_pen(item)


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
@pytest.mark.parametrize('pii_enabled', [True, False])
def test_comp_and_pen_batch_process_with_encrypted_fields(
    notify_db_session, mocker, sample_template, pii_enabled
) -> None:
    """
    Verify that records with encrypted fields are handled correctly.
    Encrypted fields should be preferred over unencrypted fields.
    """

    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mocker.patch.dict('os.environ', {'PII_ENABLED': str(pii_enabled)})

    mock_send = mocker.patch(
        'app.notifications.send_notifications.send_to_queue_for_recipient_info_based_on_recipient_identifier'
    )
    mocker.patch('app.notifications.send_notifications.send_notification_to_queue')

    # Pre-encrypt values so they can be decrypted downstream
    encrypted_vaprofile_1 = PiiVaProfileID('57').get_encrypted_value()
    encrypted_vaprofile_2 = PiiVaProfileID('43627').get_encrypted_value()
    encrypted_pid_1 = PiiPid('55').get_encrypted_value()
    encrypted_pid_2 = PiiPid('42').get_encrypted_value()

    records = [
        {
            'participant_id': '55',
            'payment_amount': '55.56',
            'vaprofile_id': '57',
            'encrypted_participant_id': encrypted_pid_1,
            'encrypted_vaprofile_id': encrypted_vaprofile_1,
        },
        {
            'participant_id': '42',
            'payment_amount': '42.42',
            'vaprofile_id': '43627',
            'encrypted_participant_id': encrypted_pid_2,
            'encrypted_vaprofile_id': encrypted_vaprofile_2,
        },
    ]

    comp_and_pen_batch_process(records)

    notifications = notify_db_session.session.scalars(select(Notification)).all()

    try:
        assert mock_send.call_count == len(records), 'Should have been called for each record.'
        assert len(notifications) == len(records), 'Should have created a new notification for each record.'

        original_vaprofile_ids = ['57', '43627']
        for index, notification in enumerate(notifications):
            assert len(notification.recipient_identifiers) == 1
            va_profile_id = notification.recipient_identifiers[IdentifierType.VA_PROFILE_ID.value].id_value
            if pii_enabled:
                decrypted = PiiVaProfileID(va_profile_id, True).get_pii()
            else:
                decrypted = va_profile_id
            assert decrypted == original_vaprofile_ids[index]
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


def test_comp_and_pen_batch_process_decryption_failure_continues(mocker, sample_template) -> None:
    """When decryption fails for a record, processing should continue with remaining records."""
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mock_resolve = mocker.patch(
        'app.celery.process_comp_and_pen._resolve_pii_for_comp_and_pen',
        side_effect=[Exception('Decryption failed'), ('resolved_pid', 'resolved_va')],
    )
    mock_bypass = mocker.patch('app.celery.process_comp_and_pen.send_notification_bypass_route')
    mock_logger = mocker.patch('app.celery.process_comp_and_pen.current_app.logger')

    records = [
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        {'participant_id': '42', 'payment_amount': '42.42', 'vaprofile_id': '43627'},
    ]

    comp_and_pen_batch_process(records)

    # First record fails decryption, second succeeds
    assert mock_resolve.call_count == 2
    assert mock_bypass.call_count == 1, 'Only the second record should have been sent'
    mock_logger.exception.assert_called_once()


def test_comp_and_pen_batch_process_missing_attribute(mocker, sample_template) -> None:
    """When a required attribute is missing from the record, it should log an exception and skip that record."""
    template = sample_template()
    mocker.patch(
        'app.celery.process_comp_and_pen.lookup_notification_sms_setup_data',
        return_value=(template.service, template, str(template.service.get_default_sms_sender_id())),
    )

    mock_bypass = mocker.patch('app.celery.process_comp_and_pen.send_notification_bypass_route')
    mock_logger = mocker.patch('app.celery.process_comp_and_pen.current_app.logger')

    records = [
        {'participant_id': '55', 'payment_amount': '55.56', 'vaprofile_id': '57'},
        {'payment_amount': '42.42', 'vaprofile_id': '43627'},  # Missing participant_id
    ]

    comp_and_pen_batch_process(records)

    assert mock_bypass.call_count == 1, 'Only the first record should have been sent'
    mock_logger.exception.assert_called_once()
