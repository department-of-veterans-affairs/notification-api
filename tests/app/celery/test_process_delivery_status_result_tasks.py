import datetime
import pytest
from app.celery import process_delivery_status_result_tasks
from app.dao import notifications_dao
from app.clients.sms.twilio import TwilioSMSClient
from tests.app.db import create_notification
from celery.exceptions import Retry
from app.dao.service_callback_api_dao import (save_service_callback_api)
from app.models import ServiceCallback, WEBHOOK_CHANNEL_TYPE, NOTIFICATION_SENT, DELIVERY_STATUS_CALLBACK_TYPE


# test that celery will start processing event when sqs messaging is enabled
def test_create_notification(mocker, db_session, sample_template):

    # create a notification
    test_reference = 'sms-reference-1'
    create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
    notification = notifications_dao.dao_get_notification_by_reference(test_reference)
    assert notification.status == 'sending'


# we want to test that celery task will fail when invalid provider is given
def test_with_correct_data(mocker, db_session, sample_template, sample_service, sample_notification):
    test_reference = 'sms-reference-1'
    translate_return_value = {
        "payload": "eyJhcmdzIjogW3siTWVzc2FnZSI6IHsiYm9keSI6ICJSYXdEbHJEb25lRGF0ZT0yMzAzMDkyMDI",
        "reference": "MessageSID",
        "record_status": "sent",
    }
    message = {'message': {
        'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHV'
                'zPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZ'
                'NZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIxMjIyMzMzNDQ0NCZB'
                'cGlWZXJzaW9uPTIwMTAtMDQtMDE=',
        'provider': 'twilio'}}

    mock_clients = mocker.patch('app.clients')
    mock_sms_client = mocker.patch('app.clients.sms.SmsClient')
    mock_twilio_client_method = mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                                             return_value=translate_return_value)
    mock = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, False)
    )

    assert process_delivery_status_result_tasks.process_delivery_status(event=message)

# we want to test that celery task will fail when invalid provider is given
def test_without_message(mocker, db_session, sample_template, sample_service, sample_notification):
    test_reference = 'sms-reference-1'
    translate_return_value = {
        "payload": "eyJhcmdzIjogW3siTWVzc2FnZSI6IHsiYm9keSI6ICJSYXdEbHJEb25lRGF0ZT0yMzAzMDkyMDI",
        "reference": "MessageSID",
        "record_status": "sent",
    }
    message = {'messag': {
        'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHV'
                'zPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZ'
                'NZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIxMjIyMzMzNDQ0NCZB'
                'cGlWZXJzaW9uPTIwMTAtMDQtMDE=',
        'provider': 'twilio'}}

    mock_clients = mocker.patch('app.clients')
    mock_sms_client = mocker.patch('app.clients.sms.SmsClient')
    mock_twilio_client_method = mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                                             return_value=translate_return_value)
    mock = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, False)
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=message)
