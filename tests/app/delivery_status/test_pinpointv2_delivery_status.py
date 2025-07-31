import base64
import json
import pytest
from flask import url_for


class TestPinpointV2DeliveryStatus:
    @pytest.fixture
    def pinpoint_sms_voice_v2_data(self):
        """Fixture providing sample PinpointSMSVoiceV2 data for testing"""
        pinpoint_records = {
            'Records': [
                {
                    'event_type': '_SMS.SUCCESS',
                    'event_timestamp': '2025-07-31T12:00:00.000Z',
                    'attributes': {
                        'record_status': 'DELIVERED',
                        'destination_phone_number': '+15551234567',
                        'message_id': 'test-message-id-123',
                        'iso_country_code': 'US',
                        'mms': False,
                        'sms_type': 'Transactional',
                    },
                    'client_context': {'source': 'test-source'},
                    'metrics': {'price_in_millicents_usd': 75},
                },
                {
                    'event_type': '_SMS.SUCCESS',
                    'event_timestamp': '2025-07-31T12:01:00.000Z',
                    'attributes': {
                        'record_status': 'DELIVERED',
                        'destination_phone_number': '+15559876543',
                        'message_id': 'test-message-id-456',
                        'iso_country_code': 'US',
                        'mms': False,
                        'sms_type': 'Transactional',
                    },
                    'client_context': {'source': 'test-source'},
                    'metrics': {'price_in_millicents_usd': 75},
                },
            ]
        }

        # Encode the data as it would come from firehose (base64 encoded in SNS message)
        encoded_data = base64.b64encode(json.dumps(pinpoint_records).encode('utf-8')).decode('utf-8')

        return {'raw_records': pinpoint_records, 'encoded_data': encoded_data, 'sns_payload': {'Message': encoded_data}}

    @pytest.mark.parametrize(
        'post_json',
        [
            # Test Empty SNS message
            {},
            # Test Basic SNS message with empty records
            {'Message': base64.b64encode(json.dumps({'Records': []}).encode('utf-8')).decode('utf-8')},
            # Test Single SMS success record
            {
                'Message': base64.b64encode(
                    json.dumps(
                        {
                            'Records': [
                                {
                                    'event_type': '_SMS.SUCCESS',
                                    'event_timestamp': '2025-07-31T12:00:00.000Z',
                                    'attributes': {
                                        'record_status': 'DELIVERED',
                                        'destination_phone_number': '+15551234567',
                                        'message_id': 'test-msg-123',
                                    },
                                }
                            ]
                        }
                    ).encode('utf-8')
                ).decode('utf-8')
            },
        ],
    )
    def test_post_delivery_status(self, client, mocker, post_json):
        mocker.patch('app.delivery_status.rest.process_pinpoint_v2_receipt_results.apply_async')
        mocker.patch('app.delivery_status.rest.get_notification_platform_status')

        response = client.post(url_for('pinpoint_v2.handler'), json=post_json)

        assert response.status_code == 200
        assert response.json == {'status': 'received'}

    def test_post_delivery_status_happy_path_with_pinpoint_sms_voice_v2_data(
        self, client, mocker, pinpoint_sms_voice_v2_data
    ):
        """Test the happy path with expected PinpointSMSVoiceV2 data from firehose"""

        mock_celery_task = mocker.patch('app.delivery_status.rest.process_pinpoint_v2_receipt_results.apply_async')

        mock_sms_status_record = mocker.Mock()
        mock_sms_status_record.reference = 'test-reference-123'

        # Use the fixture data
        request_payload = pinpoint_sms_voice_v2_data['sns_payload']

        response = client.post(url_for('pinpoint_v2.handler'), json=request_payload)

        assert response.status_code == 200
        assert response.json == {'status': 'received'}

        # Verify celery task was called correctly
        assert mock_celery_task.call_count == 2

        first_call_args = mock_celery_task.call_args_list[0][0][0]
        assert first_call_args[0] == mock_sms_status_record  # SmsStatusRecord
        assert first_call_args[1] == '2025-07-31T12:00:00.000Z'  # event_timestamp

        second_call_args = mock_celery_task.call_args_list[1][0][0]
        assert second_call_args[0] == mock_sms_status_record  # SmsStatusRecord
        assert second_call_args[1] == '2025-07-31T12:01:00.000Z'  # event_timestamp
