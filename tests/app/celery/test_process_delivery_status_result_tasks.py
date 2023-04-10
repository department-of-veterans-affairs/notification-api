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
            "provider": "twilio"
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
def sample_sqs_message_with_twilio_provider_name():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        "provider": "twilio"
    }


# confirmed: all below test case are dependent on valid fixtures
def test_fixture_has_required_attributes(notify_db_session, sample_delivery_status_result_message):
    """Test that celery event contains "message" """
    message = sample_delivery_status_result_message.get("message")
    provider_name = message.get("provider")
    body = message.get("body")

    assert message is not None
    assert provider_name is not None
    assert body is not None


# confirmed: task should retry when incoming message does not contain a message attribute
def test_celery_event_with_missing_message_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    # remove message (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.pop("message")

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirmed: task should retry when incoming message does not contain provider attribute
# todo: make sure this is still true
def test_celery_event_with_missing_provider_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    # remove provider (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.get("message").pop("provider")

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirm: task should retry when incoming message does not contain body attribute
def test_celery_event_with_missing_body_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    # remove body (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.get("message").pop("body")

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirmed: task should retry when incoming message has invalid message attribute
def test_celery_event_with_invalid_message_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is invalid from the CeleryEvent message"""

    # remove message (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message["message"] = {'key': 'value'}

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirmed: task should retry when incoming message has invalid provider attribute
def test_celery_event_with_invalid_provider_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is invalid from the CeleryEvent message"""

    # remove provider (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.get("message")["provider"] = "abc123"

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirm: task should retry when incoming message does not contain body attribute
def test_celery_event_with_invalid_body_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    # remove body (key) from the sample_delivery_status_result_message
    sample_delivery_status_result_message.get("message")["body"] = "body"

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# confirm: make sure we are able to properly parse a celery event
def test_parse_celery_event_with_valid_sqs_message(notify_db_session, sample_delivery_status_result_message):
    """Test that celery event can be parsed"""

    sqs_message, provider_name, body = process_delivery_status_result_tasks._parse_celery_event(
        event=sample_delivery_status_result_message)

    # check datatypes
    assert isinstance(sqs_message, dict)
    assert isinstance(provider_name, str)
    assert isinstance(body, str)

    # check values
    assert len(sqs_message.keys()) == 2
    assert len(sqs_message.get("body")) > 200
    assert sqs_message.get("provider") == "twilio"


# integration test cases: incoming message did not contain a valid provider
def test_with_invalid_provider(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification,
        sample_template
):
    """Test that celery will retry the task if provider doesnt exist then self.retry is called"""

    # change message['provider'] to invalid provider name
    sample_delivery_status_result_message["message"]["provider"] = "abc"

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(
            event=sample_delivery_status_result_message
        )


# integration test: attempt_to_get_notification says that we must retry
# confirmed passing
def test_attempt_get_notification_triggers_should_retry(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification, sample_template
):
    """
    Test scenario for when attempt_to_get_notification could not find the record
    """

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, True, False),
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# integration test: attempt_to_get_notification says do not retry but the notification object is None
def test_attempt_to_get_notification_none(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification, sample_template
):
    """We want to test that attempt_to_get_notification triggers a celery Retry when None"""

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(None, False, False),
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# integration test case: translation of delivery status returned a None object
# confirm: pass
def test_none_notification_platform_status_triggers_retry(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification
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


# confirm: pass
def test_should_exit(mocker, notify_db_session, sample_delivery_status_result_message, sample_notification):
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
        sample_template
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
# confirm pass
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


# confirm: pass
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


# todo: would like to get rid of this code block
# here we test invalid provider name
# def test_get_provider_info_with_invalid_provider(
#         notify_db_session, sample_notification_platform_status, sample_sqs_message):
#     with pytest.raises(ValueError):
#         process_delivery_status_result_tasks._get_provider_info(sample_sqs_message)
#
#
# # here we test all valid provider names
# @pytest.mark.parametrize('provider_name', ['twilio'])
# def test_get_provider_info_with_valid_provider(
#         notify_db_session, sample_notification_platform_status, sample_sqs_message, provider_name):
#     # default provider_name to in sample to whatever is in the list
#     sample_sqs_message['provider'] = provider_name
#
#     # now supply the sample to the function we want to test
#     provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(sample_sqs_message)
#
#     # parameterized provider_name should match the output from _get_provider_info
#     # and it should also match the provider.name
#     assert provider_name == provider_name_output == provider.name
#
#
# # here we test the default setting which should go to pinpoint
# def test_get_provider_info_with_no_provider(
#         notify_db_session, sample_notification_platform_status, sample_sqs_message_without_provider_name,
#         provider_name):
#     # now supply the sample to the function we want to test
#     provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(
#         sample_sqs_message_without_provider_name)
#
#     # parameterized provider_name should match the output from _get_provider_info
#     # and it should also match the provider.name
#     assert provider_name == provider_name_output == provider.name
