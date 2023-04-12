import pytest
from freezegun import freeze_time
from app.celery.process_delivery_status_result_tasks import (
    process_delivery_status,
    attempt_to_get_notification,
    _get_provider_info,
    _get_notification_parameters
)

from celery.exceptions import Retry
from tests.app.db import create_notification
import datetime
from app.models import Notification


class MockCeleryTask:
    """A class to represent a CeleryTask """

    def retry(self, queue=None):
        raise Retry()


@pytest.fixture
def sample_translate_return_value():
    """ sample response from translate_delivery_status() """
    return {
        "payload": "eyJhcmdzIjogW3siTWVzc2FnZSI6IHsiYm9keSI6ICJSYXdEbHJEb25lRGF0ZT0yMzAzMDkyMDI",
        "reference": "MessageSID",
        "record_status": "sent",
    }


@pytest.fixture
def sample_delivery_status_result_message():
    """ sample celery event for process_delivery_status() task """
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
    """ sample response notification_platform_status """
    return {
        "payload": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU"
                   "3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enom"
                   "RnJvbT0lMkIxMjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        'reference': 'SMyyy',
        'record_status': 'delivered'
    }


@pytest.fixture()
def sample_sqs_message_with_provider():
    """ sample of valid sqs_message after extraction from celery event """
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        "provider": "sms"

    }


@pytest.fixture()
def sample_sqs_message_with_twilio_provider():
    """ sample of twilio sqs_message after extraction from celery event """
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        "provider": "twilio"
    }


@pytest.fixture()
def sample_sqs_message_without_provider():
    """ sample of invalid sqs_message after extraction from celery event """
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE="
    }


def test_celery_event_with_missing_message_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message["message"]

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_celery_event_with_missing_provider_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message["message"]["provider"]

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_celery_event_with_missing_body_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message["message"]["body"]

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_celery_event_with_invalid_provider_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is invalid from the CeleryEvent message"""

    sample_delivery_status_result_message["message"]["provider"] = "abc123"

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_celery_event_with_invalid_body_attribute(notify_db_session, sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    sample_delivery_status_result_message["message"]["body"] = "body"

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_get_provider_info_with_no_provider_raises_retry(
        notify_db_session,
        sample_notification_platform_status,
        sample_sqs_message_without_provider
):
    """ Test get_provider_info() raises celery.exception.retry() when no provider is given by the celery event """

    with pytest.raises(Retry):
        _get_provider_info(MockCeleryTask(), sample_sqs_message_without_provider)


def test_get_provider_info_with_invalid_provider_raises_retry(
        notify_db_session,
        sample_sqs_message_with_provider
):
    """Test that _get_provider_info() will raise a celery retry when sqs message has an invalid provider"""

    sample_sqs_message_with_provider['provider'] = "abc"

    # now supply the sample to the function we want to test with the expectation of failure
    with pytest.raises(Retry):
        _get_provider_info(MockCeleryTask(), sample_sqs_message_with_provider)


def test_get_provider_info_with_twilio(
        notify_db_session,
        sample_notification_platform_status,
        sample_sqs_message_with_provider
):
    sample_sqs_message_with_provider['provider'] = 'twilio'

    # now supply the sample to the function we want to test
    provider_name_output, provider = _get_provider_info(
        MockCeleryTask(),
        sample_sqs_message_with_provider
    )

    assert provider.name == 'twilio'
    assert provider_name_output == 'twilio'


def test_attempt_to_get_notification_with_good_data(
        notify_db_session,
        sample_notification_platform_status,
        sample_template
):
    """Test that we will exit the celery task when sqs message matches what has already been reported in the database"""

    notification_status = 'delivered'
    reference = 'SMyyy'

    # create notification object
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status
    )

    # attempt to get the notification object that we created from the database
    notification, should_retry, should_exit = attempt_to_get_notification(
        reference, notification_status
    )

    # check the values that attempt_to_get_notification() return against what we sent
    assert isinstance(notification, Notification)
    assert notification.status == notification_status
    assert notification.reference == reference

    # SQS callback received matches the data in the database, so we should exit the celery task
    assert not should_retry
    assert should_exit


def test_attempt_to_get_notification_duplicate_notification(
        notify_db_session,
        sample_notification_platform_status,
        sample_template
):

    """Test that duplicate notifications will make notification = None, should_retry=False, should_exit=True"""

    notification_status = 'delivered'
    reference = 'SMyyy'

    # create notification object
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status
    )

    # create duplicate notification
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status
    )

    # should trigger a "MultipleResultsFound" when we attempt to get the notification object
    notification, should_retry, should_exit = attempt_to_get_notification(
        reference, notification_status
    )

    # Remember: celery task will trigger a retry when notification = None
    assert notification is None

    # should_exit=True because of the "MultipleResultsFound" exception
    assert not should_retry
    assert should_exit


def test_process_delivery_status_with_invalid_notification_raises_retry(
        notify_db_session,
        sample_delivery_status_result_message
):
    """ Notification is invalid because there are no notifications in the database"""
    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_none_notification_platform_status_triggers_retry(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification
):
    """Verify that retry is triggered if translate_delivery_status returns None"""

    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status", return_value=None)

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


@freeze_time('1900-06-13 13:00')
@pytest.mark.xfail(reason="Celery Task cannot properly determine time the message was originally received", run=False)
def test_attempt_to_get_notification_older_than_five_minutes(
        notify_db_session,
        sample_delivery_status_result_message,
        sample_template
):
    """Celery Task should retry whenever attempt_to_get_notification() could not find a matching notification"""

    notification, should_retry, should_exit = attempt_to_get_notification('SMyyy', 'delivered')
    assert notification is None
    assert not should_retry
    assert should_exit


def test_process_delivery_status_should_retry_preempts_exit(
        notify_db_session,
        sample_delivery_status_result_message
):
    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


def test_process_delivery_status_with_valid_message_with_no_payload(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_template
):
    """Test that celery task will complete if correct data is provided"""

    notification = create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='sent',

    )

    callback_mock = mocker.patch("app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task")
    assert process_delivery_status(event=sample_delivery_status_result_message)
    callback_mock.assert_called_once_with(notification, {})


def test_process_delivery_status_with_valid_message_with_payload(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_template
):
    """Test that celery task will complete if correct data is provided"""

    notification = create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='sent',

    )

    mocker.patch("app.celery.process_delivery_status_result_tasks._get_include_payload_status", returns=True)
    callback_mock = mocker.patch("app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task")
    assert process_delivery_status(event=sample_delivery_status_result_message)
    callback_mock.assert_called_once()


def test_get_notification_parameters(notify_db_session, sample_notification_platform_status):
    (payload,
     reference,
     notification_status,
     number_of_message_parts,
     price_in_millicents_usd) = _get_notification_parameters(
        sample_notification_platform_status
    )

    """Test our ability to get parameters such as payload or reference from notification_platform_status"""

    assert notification_status == 'delivered'
    assert reference == 'SMyyy'
    assert number_of_message_parts == 1
    assert price_in_millicents_usd >= 0
    assert isinstance(payload, str)
