import datetime
import pytest
from app.celery import process_delivery_status_result_tasks
from app.dao import notifications_dao
from app.clients.sms.twilio import TwilioSMSClient
from tests.app.db import create_notification
from celery.exceptions import Retry
from app.dao.service_callback_api_dao import (save_service_callback_api)
from app.models import ServiceCallback, WEBHOOK_CHANNEL_TYPE, NOTIFICATION_SENT, DELIVERY_STATUS_CALLBACK_TYPE


@pytest.fixture
def sample_translate_return_value():
    return {
        "payload": "eyJhcmdzIjogW3siTWVzc2FnZSI6IHsiYm9keSI6ICJSYXdEbHJEb25lRGF0ZT0yMzAzMDkyMDI",
        "reference": "MessageSID",
        "record_status": "sent",
    }


@pytest.fixture
def sample_delivery_status_result_message():
    return {
        'message': {
            'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHV'
                    'zPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZ'
                    'NZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIxMjIyMzMzNDQ0NCZB'
                    'cGlWZXJzaW9uPTIwMTAtMDQtMDE=',
            'provider': 'twilio'
        }
    }


# Test if message doesnt exist then self.retry is called
def test_without_message(mocker, db_session, sample_delivery_status_result_message,
                         sample_translate_return_value, sample_notification):
    # remove message (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.pop('message')
    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.SmsClient')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                 return_value=sample_translate_return_value)
    mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, False)
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# Test if provider doesnt exist then self.retry is called
def test_without_provider(mocker, db_session, sample_delivery_status_result_message,
                          sample_translate_return_value, sample_notification):
    # change message['provider'] to invalid provider name
    sample_delivery_status_result_message['message']['provider'] = 'abc'
    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.SmsClient')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                 return_value=sample_translate_return_value)
    mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, False)
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# we want to test that celery task will retry when should_retry=True
def test_with_should_retry(mocker, db_session, sample_delivery_status_result_message,
                           sample_translate_return_value, sample_notification):
    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.SmsClient')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                 return_value=sample_translate_return_value)
    mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, True, False)
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# we want to test that celery task will exit when should_exit=True
def test_with_should_exit(mocker, db_session, sample_delivery_status_result_message,
                           sample_translate_return_value, sample_notification):
    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.SmsClient')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                 return_value=sample_translate_return_value)
    mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, True)
    )

    assert not process_delivery_status_result_tasks.process_delivery_status(
        event=sample_delivery_status_result_message)


# we want to test that celery task will succeed when correct data is given
def test_with_correct_data(mocker, db_session, sample_delivery_status_result_message,
                           sample_translate_return_value, sample_notification):
    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.SmsClient')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status',
                 return_value=sample_translate_return_value)
    mocker.patch(
        'app.celery.process_delivery_status_result_tasks.attempt_to_get_notification',
        return_value=(sample_notification, False, False)
    )

    assert process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)

# * verify that if translate_delivery_status throws an keyerror then self.retry is called
# * verify that if translate_delivery_status returns None then self.retry is called
