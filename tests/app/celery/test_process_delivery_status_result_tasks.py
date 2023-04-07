import pytest
from app.celery import process_delivery_status_result_tasks
from celery.exceptions import Retry
from tests.app.db import create_notification
import datetime
from app.models import Notification


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
        "message": {
            "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHV"
                    "zPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZ"
                    "NZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIxMjIyMzMzNDQ0NCZB"
                    "cGlWZXJzaW9uPTIwMTAtMDQtMDE=",
            "provider": "twilio",
        }
    }


@pytest.fixture()
def sample_notification_platform_status():
    return {
        "payload": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU"
                   "3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enom"
                   "RnJvbT0lMkIxMjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        'reference': 'SMyyy',
        'record_status': 'delivered'
    }


@pytest.fixture()
def sample_sqs_message():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE="
    }


# integration test cases: incoming message does not contain a message property
def test_event_message_invalid_message(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    # remove message (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.pop("message")

    # mock translate_delivery_status() when called within process_delivery_status_result_tasks()
    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.SmsClient")
    mocker.patch(
        "app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status",
        return_value=sample_translate_return_value,
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


def test_without_provider(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """Test that celery will retry the task if provider doesnt exist then self.retry is called"""

    # change message['provider'] to invalid provider name
    sample_delivery_status_result_message["message"]["provider"] = "abc"
    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.SmsClient")

    create_notification(
        sample_template, reference='sms-reference-1',
        sent_at=datetime.datetime.utcnow(), status='sending'
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


# integration test: attempt_to_get_notification says that we must retry
def test_attempt_get_notification_triggers_should_retry(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """
    Test scenario for when attempt_to_get_notification could not find the record
    """

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, True, False),
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


# integration test: attempt_to_get_notification says do not retry but the notification object is None
def test_attempt_to_get_notification_none(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """We want to test that attempt_to_get_notification triggers a celery Retry when None"""

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(None, False, False),
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


# integration test: body is missing from the incoming message
def test_missing_body_triggers_retry(
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """Verify that retry is triggered if translate_delivery_status is given a body does not exist"""
    # change message['body'] to invalid body
    sample_delivery_status_result_message["message"].pop("body")
    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )



# integration test case: translation of delivery status returned a None object
def test_none_notification_platform_status_triggers_retry(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """verify that retry is triggered if translate_delivery_status is returns a None"""

    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.SmsClient")
    mocker.patch(
        "app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status",
        return_value=None
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# integration translate_delivery_status shou
def test_invalid_body_triggers_retry(
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """
    verify that retry is triggered if translate_delivery_status is given a body is missing properties
    """

    # change message['body'] to invalid body
    sample_delivery_status_result_message["message"]["body"] = ""
    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


def test_should_exit(
    mocker, notify_db_session, sample_delivery_status_result_message, sample_notification
):
    """Test that celery task will "exit" if multiple notifications were found"""
    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, False, True),
    )

    assert not process_delivery_status_result_tasks.process_delivery_status(
        event=sample_delivery_status_result_message
    )


def test_with_correct_data(
    mocker,
    notify_db_session,
    sample_delivery_status_result_message,
    sample_translate_return_value,
    sample_notification,
):
    """Test that celery task will complete if correct data is provided"""

    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.SmsClient")
    mocker.patch(
        "app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status",
        return_value=sample_translate_return_value,
    )

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, False, False),
    )

    assert process_delivery_status_result_tasks.process_delivery_status(
        event=sample_delivery_status_result_message
    )


# test notification_platform_status has data
def test_get_notification_parameters(notify_db_session, sample_notification_platform_status):
    (payload,
     reference,
     notification_status,
     number_of_message_parts,
     price_in_millicents_usd) = process_delivery_status_result_tasks._get_notification_parameters(
        sample_notification_platform_status
    )

    assert notification_status == 'delivered', 'notification_status should have been delivered'
    assert reference == 'SMyyy', 'reference is not SMyyy'
    assert number_of_message_parts == 1, 'number of parts should be 1 '
    assert price_in_millicents_usd >= 0, 'price_in_millicents_usd should be >= 0 '
    assert isinstance(payload, str), 'payload should have been a string'


def test_attempt_to_get_notification(notify_db_session, sample_notification_platform_status, sample_template):
    notification_status = 'delivered'
    reference = 'SMyyy'

    create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='delivered'
    )

    notification, should_retry, should_exit = process_delivery_status_result_tasks.attempt_to_get_notification(
        reference, notification_status
    )

    assert isinstance(notification, Notification)
    assert notification.status == 'delivered'
    assert notification.reference == 'SMyyy'


# here we test invalid provider name
def test_get_provider_info_with_invalid_provider(
        notify_db_session, sample_notification_platform_status, sample_sqs_message):
    with pytest.raises(ValueError):
        process_delivery_status_result_tasks._get_provider_info(sample_sqs_message)


# here we test all valid provider names
@pytest.mark.parametrize('provider_name', ['twilio'])
def test_get_provider_info_with_valid_provider(
        notify_db_session, sample_notification_platform_status, sample_sqs_message, provider_name):
    # default provider_name to in sample to whatever is in the list
    sample_sqs_message['provider'] = provider_name

    # now supply the sample to the function we want to test
    provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(sample_sqs_message)

    # parameterized provider_name should match the output from _get_provider_info
    # and it should also match the provider.name
    assert provider_name == provider_name_output == provider.name


# here we test the default setting which should go to pinpoint
def test_get_provider_info_with_no_provider(
        notify_db_session, sample_notification_platform_status, sample_sqs_message, provider_name):
    # now supply the sample to the function we want to test
    provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(sample_sqs_message)

    # parameterized provider_name should match the output from _get_provider_info
    # and it should also match the provider.name
    assert provider_name == provider_name_output == provider.name
