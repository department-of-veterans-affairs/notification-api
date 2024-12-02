import os


from unittest.mock import patch

from app.celery import process_ses_receipts_tasks
from app.constants import SMS_TYPE
from app.models import Notification


class TestSendNotificationStatusesToVAProfile:
    mock_sms_notification_data = {
        'id': '2e9e6920-4f6f-4cd5-9e16-fc306fe23867',
        'reference': None,
        'to': '(732)846-6666',
        'status': 'delivered',
        'status_reason': '',
        'created_at': '2024-07-25T10:00:00.0',
        'completed_at': '2024-07-25T11:00:00.0',
        'sent_at': '2024-07-25T11:00:00.0',
        'notification_type': SMS_TYPE,
        'provider': 'twilio',
    }

    @patch('app.va.va_profile.va_profile_client.requests.post')
    def test_can_send_sms_notification_status_to_va_profile(self, mock_post, notify_api, mocker):
        mocker.patch.dict(os.environ, {'VA_PROFILE_EMAIL_STATUS_ENABLED': 'True'})

        sms_notification = Notification(
            id=self.mock_sms_notification_data['id'],
            reference=self.mock_sms_notification_data['reference'],
            to=self.mock_sms_notification_data['to'],
            status=self.mock_sms_notification_data['status'],
            status_reason=self.mock_sms_notification_data['status_reason'],
            created_at=self.mock_sms_notification_data['created_at'],
            completed_at=self.mock_sms_notification_data['completed_at'],
            sent_at=self.mock_sms_notification_data['sent_at'],
            notification_type=self.mock_sms_notification_data['notification_type'],
        )

        process_ses_receipts_tasks.check_and_queue_va_profile_email_status_callback(sms_notification)

        expected_url = 'http://mock.vaprofile.va.gov/contact-information-vanotify/notify/status'
        expected_payload = {
            'id': str(sms_notification.id),
            'reference': sms_notification.client_reference,
            'to': sms_notification.to,
            'status': sms_notification.status,
            'status_reason': sms_notification.status_reason,
            'created_at': sms_notification.created_at,
            'completed_at': sms_notification.updated_at,
            'sent_at': sms_notification.sent_at,
            'notification_type': sms_notification.notification_type,
            'provider': sms_notification.sent_by,
        }
        mock_post.assert_called_once_with(expected_url, json=expected_payload)

    # def test_ut_check_and_queue_va_profile_email_status_callback_does_not_queue_task_if_feature_disabled(self, mocker):
    #     mocker.patch('app.celery.process_ses_receipts_tasks.is_feature_enabled', return_value=False)
    #     mock_send_email_status = mocker.patch(
    #         'app.celery.process_ses_receipts_tasks.send_email_status_to_va_profile.apply_async'
    #     )
    #     mock_notification = mocker.patch('app.celery.process_ses_receipts_tasks.Notification')

    #     process_ses_receipts_tasks.check_and_queue_va_profile_email_status_callback(mock_notification)

    #     mock_send_email_status.assert_not_called()

    # def test_ut_check_and_queue_va_profile_email_status_callback_queues_task_if_feature_enabled(self, mocker):
    #     mocker.patch('app.celery.process_ses_receipts_tasks.is_feature_enabled', return_value=True)
    #     mock_send_email_status = mocker.patch(
    #         'app.celery.process_ses_receipts_tasks.send_email_status_to_va_profile.apply_async'
    #     )
    #     mock_notification = mocker.patch('app.celery.process_ses_receipts_tasks.Notification')

    #     process_ses_receipts_tasks.check_and_queue_va_profile_email_status_callback(mock_notification)

    #     mock_send_email_status.assert_called_once()

    # def test_ut_send_email_status_to_va_profile(self, mocker):
    #     mock_send_va_profile_email_status = mocker.patch(
    #         'app.celery.process_ses_receipts_tasks.va_profile_client.send_va_profile_email_status'
    #     )

    #     process_ses_receipts_tasks.send_email_status_to_va_profile(self.mock_notification_data)

    #     mock_send_va_profile_email_status.assert_called_once_with(self.mock_notification_data)

    # def test_ut_send_email_status_to_va_profile_raises_auto_retry_exception(self, mocker):
    #     mock_send_va_profile_email_status = mocker.patch(
    #         'app.celery.process_ses_receipts_tasks.va_profile_client.send_va_profile_email_status',
    #         side_effect=[ConnectTimeout, ReadTimeout],
    #     )

    #     with pytest.raises(AutoRetryException):
    #         process_ses_receipts_tasks.send_email_status_to_va_profile(self.mock_notification_data)

    #     mock_send_va_profile_email_status.assert_called_once()
