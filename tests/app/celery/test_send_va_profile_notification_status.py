import os
from datetime import datetime
from unittest.mock import patch

from app.celery.send_va_profile_notification_status import check_and_queue_va_profile_email_status_callback
from app.constants import EMAIL_TYPE, SMS_TYPE
from app.models import Notification


class TestSendNotificationStatusesToVAProfile:
    mock_sms_notification_data = {
        'id': '2e9e6920-4f6f-4cd5-9e16-fc306fe23867',
        'reference': None,
        'to': '(732)846-6666',
        'status': 'delivered',
        'status_reason': '',
        'created_at': datetime.fromisoformat('2024-07-25T10:00:00'),
        'completed_at': datetime.fromisoformat('2024-07-25T11:00:00'),
        'sent_at': datetime.fromisoformat('2024-07-25T11:00:00'),
        'notification_type': SMS_TYPE,
        'sent_by': 'twilio',
    }

    mock_email_notification_data = {
        'id': '2e9e6920-4f6f-4cd5-9e16-fc306fe23867',
        'reference': None,
        'to': 'test@email.com',
        'status': 'delivered',
        'status_reason': '',
        'created_at': datetime.fromisoformat('2024-07-25T10:00:00'),
        'completed_at': datetime.fromisoformat('2024-07-25T11:00:00'),
        'sent_at': datetime.fromisoformat('2024-07-25T11:00:00'),
        'notification_type': EMAIL_TYPE,
        'sent_by': 'ses',
    }

    @patch('app.va.va_profile.va_profile_client.requests.post')
    def test_can_send_sms_notification_status_to_va_profile(self, mock_post, notify_api, mocker):
        mocker.patch.dict(os.environ, {'VA_PROFILE_SMS_STATUS_ENABLED': 'True'})

        sms_notification = Notification(**self.mock_sms_notification_data)

        check_and_queue_va_profile_email_status_callback(sms_notification)

        va_profile_url = os.getenv('VA_PROFILE_URL')
        expected_url = f'{va_profile_url}/contact-information-vanotify/notify/status'

        expected_payload = {
            'id': str(sms_notification.id),
            'reference': sms_notification.reference,
            'to': sms_notification.to,
            'status': sms_notification.status,
            'status_reason': sms_notification.status_reason,
            'created_at': sms_notification.created_at.isoformat() + '.000000Z',
            'completed_at': None,
            'sent_at': sms_notification.sent_at.isoformat() + '.000000Z',
            'notification_type': sms_notification.notification_type,
            'provider': 'twilio',
        }

        expected_headers = {'Authorization': 'Bearer '}
        expected_timeout = (30, 30)

        mock_post.assert_called_once_with(
            expected_url, json=expected_payload, headers=expected_headers, timeout=expected_timeout
        )

    @patch('app.va.va_profile.va_profile_client.requests.post')
    def test_can_send_email_notification_status_to_va_profile(self, mock_post, notify_api, mocker):
        mocker.patch.dict(os.environ, {'VA_PROFILE_SMS_STATUS_ENABLED': 'False'})

        email_notification = Notification(**self.mock_email_notification_data)

        check_and_queue_va_profile_email_status_callback(email_notification)

        va_profile_url = os.getenv('VA_PROFILE_URL')
        expected_url = f'{va_profile_url}/contact-information-vanotify/notify/status'

        expected_payload = {
            'id': str(email_notification.id),
            'reference': email_notification.reference,
            'to': email_notification.to,
            'status': email_notification.status,
            'status_reason': email_notification.status_reason,
            'created_at': email_notification.created_at.isoformat() + '.000000Z',
            'completed_at': None,
            'sent_at': email_notification.sent_at.isoformat() + '.000000Z',
            'notification_type': email_notification.notification_type,
            'provider': 'ses',
        }

        expected_headers = {'Authorization': 'Bearer '}
        expected_timeout = (30, 30)

        mock_post.assert_called_once_with(
            expected_url, json=expected_payload, headers=expected_headers, timeout=expected_timeout
        )
