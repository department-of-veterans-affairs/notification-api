import pytest
from datetime import datetime

from app.clients.sms import SmsStatusRecord
from app.constants import PINPOINT_PROVIDER, STATUS_REASON_RETRYABLE
from app.celery.process_pinpoint_v2_receipt_tasks import process_pinpoint_v2_receipt_results


class TestProcessPinpointV2ReceiptResults:
    @pytest.fixture
    def sample_sms_status_record(self):
        """Fixture providing a sample SmsStatusRecord for testing"""
        return SmsStatusRecord(
            payload=None,
            reference='test-message-id-123',
            status='delivered',
            status_reason=None,
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 0, 0, 0),
        )

    @pytest.fixture
    def retryable_sms_status_record(self):
        """Fixture providing a retryable SmsStatusRecord for testing"""
        return SmsStatusRecord(
            payload=None,
            reference='test-message-id-456',
            status='temporary-failure',
            status_reason=STATUS_REASON_RETRYABLE,
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 0, 0, 0),
        )

    def test_process_receipt_results_calls_sms_status_update(self, mocker, sample_sms_status_record):
        """Test that non-retryable status records call sms_status_update"""
        mock_sms_status_update = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_status_update')
        mock_sms_attempt_retry = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_attempt_retry')

        event_timestamp = '1722427200000'

        process_pinpoint_v2_receipt_results(sample_sms_status_record, event_timestamp)

        mock_sms_status_update.assert_called_once_with(sample_sms_status_record, event_timestamp)
        mock_sms_attempt_retry.assert_not_called()

    def test_process_receipt_results_calls_sms_attempt_retry(self, mocker, retryable_sms_status_record):
        """Test that retryable status records call sms_attempt_retry"""
        mock_sms_status_update = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_status_update')
        mock_sms_attempt_retry = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_attempt_retry')

        event_timestamp = '1722427260000'

        process_pinpoint_v2_receipt_results(retryable_sms_status_record, event_timestamp)

        mock_sms_attempt_retry.assert_called_once_with(retryable_sms_status_record, event_timestamp)
        mock_sms_status_update.assert_not_called()

    def test_process_receipt_results_with_different_status_reasons(self, mocker):
        """Test that different status reasons are handled correctly"""
        mock_sms_status_update = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_status_update')
        mock_sms_attempt_retry = mocker.patch('app.celery.process_pinpoint_v2_receipt_tasks.sms_attempt_retry')

        record_none = SmsStatusRecord(
            payload=None,
            reference='test-none',
            status='delivered',
            status_reason=None,
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 0, 0, 0),
        )

        process_pinpoint_v2_receipt_results(record_none, '1722427200000')
        mock_sms_status_update.assert_called_with(record_none, '1722427200000')
        mock_sms_attempt_retry.assert_not_called()

        # Reset mocks
        mock_sms_status_update.reset_mock()
        mock_sms_attempt_retry.reset_mock()

        # Test with different non-retryable status_reason
        record_failed = SmsStatusRecord(
            payload=None,
            reference='test-failed',
            status='permanent-failure',
            status_reason='carrier-blocked',
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 0, 0, 0),
        )

        process_pinpoint_v2_receipt_results(record_failed, '1722427260000')
        mock_sms_status_update.assert_called_with(record_failed, '1722427260000')
        mock_sms_attempt_retry.assert_not_called()
