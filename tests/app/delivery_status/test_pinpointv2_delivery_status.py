import base64
import json
from datetime import datetime

import pytest
from flask import url_for

from app.clients.sms import SmsStatusRecord
from app.constants import PINPOINT_PROVIDER
from app.feature_flags import FeatureFlag


class TestPinpointV2DeliveryStatus:
    @pytest.fixture
    def pinpoint_sms_voice_v2_data(self):
        """Fixture providing sample PinpointSMSVoiceV2 data for testing"""
        pinpoint_records = {
            'Records': [
                {
                    'eventType': 'TEXT_SUCCESSFUL',
                    'eventVersion': '1.0',
                    'eventTimestamp': 1722427200000,
                    'isFinal': True,
                    'originationPhoneNumber': '+12065550152',
                    'destinationPhoneNumber': '+15551234567',
                    'isoCountryCode': 'US',
                    'mcc': '310',
                    'mnc': '800',
                    'messageId': 'test-message-id-123',
                    'messageRequestTimestamp': 1722427199000,
                    'messageEncoding': 'GSM',
                    'messageType': 'TRANSACTIONAL',
                    'messageStatus': 'DELIVERED',
                    'messageStatusDescription': 'Message has been accepted by phone carrier',
                    'context': {'source': 'test-source'},
                    'totalMessageParts': 1,
                    'totalMessagePrice': 0.075,
                    'totalCarrierFee': 0.0,
                },
                {
                    'eventType': 'TEXT_SUCCESSFUL',
                    'eventVersion': '1.0',
                    'eventTimestamp': 1722427260000,
                    'isFinal': True,
                    'originationPhoneNumber': '+12065550152',
                    'destinationPhoneNumber': '+15559876543',
                    'isoCountryCode': 'US',
                    'mcc': '310',
                    'mnc': '800',
                    'messageId': 'test-message-id-456',
                    'messageRequestTimestamp': 1722427259000,
                    'messageEncoding': 'GSM',
                    'messageType': 'TRANSACTIONAL',
                    'messageStatus': 'DELIVERED',
                    'messageStatusDescription': 'Message has been accepted by phone carrier',
                    'context': {'source': 'test-source'},
                    'totalMessageParts': 1,
                    'totalMessagePrice': 0.075,
                    'totalCarrierFee': 0.0,
                },
            ]
        }

        # Encode the data as it would come from firehose (base64 encoded in SNS message)
        encoded_data = base64.b64encode(json.dumps(pinpoint_records).encode('utf-8')).decode('utf-8')

        return {'raw_records': pinpoint_records, 'sns_payload': {'Message': encoded_data}}

    def test_post_delivery_status_no_records(self, client, mocker):
        mocker.patch('app.delivery_status.rest.process_pinpoint_v2_receipt_results.apply_async')
        mocker.patch('app.delivery_status.rest.get_notification_platform_status')

        post_json = {'Message': base64.b64encode(json.dumps({'Records': []}).encode('utf-8')).decode('utf-8')}
        response = client.post(url_for('pinpoint_v2.handler'), json=post_json)

        assert response.status_code == 200
        assert response.json == {'status': 'received'}

    def test_post_delivery_status_multiple_records(self, client, mocker, pinpoint_sms_voice_v2_data):
        """Test the happy path with expected PinpointSMSVoiceV2 data from firehose"""

        mock_celery_task = mocker.patch('app.delivery_status.rest.process_pinpoint_v2_receipt_results.apply_async')

        mock_feature_flag = mocker.Mock(FeatureFlag)
        mock_feature_flag.value = 'PINPOINT_SMS_VOICE_V2'
        mocker.patch('app.feature_flags.os.getenv', return_value='True')

        request_payload = pinpoint_sms_voice_v2_data['sns_payload']

        response = client.post(url_for('pinpoint_v2.handler'), json=request_payload)

        expected_record_1 = SmsStatusRecord(
            payload=None,
            reference='test-message-id-123',
            status='delivered',
            status_reason=None,
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 0, 0, 0),
        )

        expected_record_2 = SmsStatusRecord(
            payload=None,
            reference='test-message-id-456',
            status='delivered',
            status_reason=None,
            message_parts=1,
            provider=PINPOINT_PROVIDER,
            price_millicents=75,
            provider_updated_at=datetime(2024, 7, 31, 12, 1, 0, 0),
        )

        assert response.status_code == 200
        assert response.json == {'status': 'received'}

        assert mock_celery_task.call_count == 2

        first_call_args = mock_celery_task.call_args_list[0][0][0]
        assert first_call_args[0] == expected_record_1
        assert first_call_args[1] == 1722427200000

        second_call_args = mock_celery_task.call_args_list[1][0][0]
        assert second_call_args[0] == expected_record_2
        assert second_call_args[1] == 1722427260000

    def test_post_delivery_status_with_validation_errors(self, client, mocker, pinpoint_sms_voice_v2_data, caplog):
        """Test that validation errors for individual records don't stop processing of other records"""

        mock_feature_flag = mocker.Mock(FeatureFlag)
        mock_feature_flag.value = 'PINPOINT_SMS_VOICE_V2'
        mocker.patch('app.feature_flags.os.getenv', return_value='True')

        mock_celery_task = mocker.patch('app.delivery_status.rest.process_pinpoint_v2_receipt_results.apply_async')
        mock_logger = mocker.patch('app.delivery_status.rest.current_app.logger')

        # Use the raw_records and modify them
        modified_records = pinpoint_sms_voice_v2_data['raw_records'].copy()

        # Make the second record invalid by removing required fields
        modified_records['Records'][1] = {
            'eventVersion': '1.0',
            'eventTimestamp': 1722427260000,
            'isFinal': True,
            # Missing eventType and messageId - this will cause validation to fail
        }

        # Add a third valid record
        modified_records['Records'].append(
            {
                'eventType': 'TEXT_SUCCESSFUL',
                'eventVersion': '1.0',
                'eventTimestamp': 1722427320000,
                'isFinal': True,
                'originationPhoneNumber': '+12065550152',
                'destinationPhoneNumber': '+15559876543',
                'isoCountryCode': 'US',
                'mcc': '310',
                'mnc': '800',
                'messageId': 'test-message-id-789',
                'messageRequestTimestamp': 1722427319000,
                'messageEncoding': 'GSM',
                'messageType': 'TRANSACTIONAL',
                'messageStatus': 'DELIVERED',
                'messageStatusDescription': 'Message has been accepted by phone carrier',
                'context': {'source': 'test-source'},
                'totalMessageParts': 1,
                'totalMessagePrice': 0.075,
                'totalCarrierFee': 0.0,
            }
        )

        modified_payload = {'Message': base64.b64encode(json.dumps(modified_records).encode('utf-8')).decode('utf-8')}

        response = client.post(url_for('pinpoint_v2.handler'), json=modified_payload)

        assert response.status_code == 200
        assert response.json == {'status': 'received'}

        # Should have processed 2 valid records, skipped 1 invalid
        assert mock_celery_task.call_count == 2

        # Check that error was logged with unknown messageId
        assert mock_logger.error.call_count == 1
        assert mock_logger.error.call_args[0] == (
            'Validation for Pinpoint SMS Voice V2 records failed: %s | Error: %s',
            'unknown messageId',
            'Invalid PinpointSMSVoiceV2 message format, unable to translate delivery status',
        )
