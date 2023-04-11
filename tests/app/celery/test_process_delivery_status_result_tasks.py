import pytest
from app.celery import process_delivery_status_result_tasks
from celery.exceptions import Retry
from tests.app.db import create_notification
import datetime
from app.models import Notification


# here we make a fake Celery Task to support the use of self
class MockCeleryTask:
    def retry(self, queue=None):
        raise Retry()


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
def sample_sqs_message():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE="
    }


@pytest.fixture()
def sample_sqs_message_with_twilio_provider():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        "provider": "twilio"
    }


@pytest.fixture()
def sample_sqs_message_without_provider():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE="
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


# test get_provider_info when no provider is given by the celery event
def test_get_provider_info_with_no_provider(
        notify_db_session, sample_notification_platform_status, sample_sqs_message_without_provider,
        provider_name):
    mock_celery_task = MockCeleryTask()

    # now supply the sample to the function we want to test
    provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(mock_celery_task,
                                                                                             sqs_message=sample_sqs_message_without_provider)

    # parameterized provider_name should match the output from _get_provider_info
    # and it should also match the provider.name
    assert provider_name == provider_name_output == provider.name


# here we test invalid provider name
def test_get_provider_info_with_invalid_provider(
        notify_db_session,
        sample_sqs_message
):
    """Test that _get_provider_info() will raise a celery retry when sqs message has an invalid provider"""

    # mock the celery task event
    mock_celery_task = MockCeleryTask()
    sample_sqs_message['provider'] = "abc"

    # now supply the sample to the function we want to test with the expectation of failure
    with pytest.raises(Retry):
        process_delivery_status_result_tasks._get_provider_info(mock_celery_task, sample_sqs_message)


# here we test all valid provider names
@pytest.mark.parametrize('provider_name', ['twilio'])
def test_get_provider_info_with_valid_provider(
        notify_db_session, sample_notification_platform_status, sample_sqs_message, provider_name):
    """Test that _get_provider_info() will return  a celery retry when sqs message has an invalid provider"""
    # default provider_name to current parameterized value
    sample_sqs_message['provider'] = provider_name

    # mock the celery task event
    mock_celery_task = MockCeleryTask()

    # now supply the sample to the function we want to test
    provider_name_output, provider = process_delivery_status_result_tasks._get_provider_info(
        mock_celery_task,
        sample_sqs_message
    )

    # parameterized provider_name should match the output from _get_provider_info
    # and it should also match the provider.name
    assert provider_name == provider_name_output == provider.name


def test_attempt_to_get_notification_with_good_data(
        notify_db_session, sample_notification_platform_status, sample_template):
    notification_status = 'delivered'
    reference = 'SMyyy'

    """Test that we will exit the celery task when sqs message matches what has already been reported in the database"""

    # create notification object
    create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='delivered'
    )

    # attempt to get the notification object that we created from the database
    notification, should_retry, should_exit = process_delivery_status_result_tasks.attempt_to_get_notification(
        reference, notification_status
    )

    # check the values that attempt_to_get_notification() return against what we sent
    assert isinstance(notification, Notification)
    assert notification.status == 'delivered'
    assert notification.reference == 'SMyyy'

    # SQS callback received matches the data in the database, so we should exit the celery task
    assert should_retry is False
    assert should_exit is True


def test_attempt_to_get_notification_duplicate_notification(
        notify_db_session, sample_notification_platform_status, sample_template):

    """Test that duplicate notifications will make notification = None, should_retry=False, should_exit=True"""

    notification_status = 'delivered'
    reference = 'SMyyy'

    # create notification object
    create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='delivered'
    )

    # create duplicate notification
    create_notification(
        sample_template,
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status='delivered'
    )

    # we should trigger a "MultipleResultsFound" when we attempt to get the notification object
    notification, should_retry, should_exit = process_delivery_status_result_tasks.attempt_to_get_notification(
        reference, notification_status
    )

    # exception which will make notification = None
    # important the Remember: celery task will trigger a retry when notification = None
    assert notification is None

    # should_exit=True because of the "MultipleResultsFound" exception
    assert should_retry is False
    assert should_exit is True


def test_attempt_to_get_notification_none(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification, sample_template
):
    """We want to test that attempt_to_get_notification triggers a celery Retry when notification is None"""

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(None, False, False),
    )

    # important the celery task will trigger a retry when notification = None and should_retry = False
    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


# integration test case: translation of delivery status returned a None object
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


def test_attempt_get_notification_triggers_should_retry(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_translate_return_value,
        sample_notification, sample_template
):
    """
    Celery Task should retry whenever attempt_to_get_notification() could not find a matching notification
    """

    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, True, False),
    )

    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=sample_delivery_status_result_message)


def test_should_exit(mocker, notify_db_session, sample_delivery_status_result_message, sample_notification):
    """Test that celery task will "exit" if multiple notifications were found"""
    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, False, True),
    )

    # celery task should return False whenever attempt_to_get_notification() says exit
    assert not process_delivery_status_result_tasks.process_delivery_status(
        event=sample_delivery_status_result_message
    )


def test_should_retry_preempts_exit(
        mocker,
        notify_db_session,
        sample_delivery_status_result_message,
        sample_notification):
    """Test that celery task will protects against race condition"""
    mocker.patch(
        "app.celery.process_delivery_status_result_tasks.attempt_to_get_notification",
        return_value=(sample_notification, True, True),
    )

    # celery task should retry whenever attempt_to_get_notification() return true on both retry and exit
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

    # todo: a way to confirm that check_and_queue_callback_task() was called


def test_get_notification_parameters(notify_db_session, sample_notification_platform_status):
    (payload,
     reference,
     notification_status,
     number_of_message_parts,
     price_in_millicents_usd) = process_delivery_status_result_tasks._get_notification_parameters(
        sample_notification_platform_status
    )

    """Test our ability to get parameters such as payload or reference from notification_platform_status"""

    assert notification_status == 'delivered', 'notification_status should have been delivered'
    assert reference == 'SMyyy', 'reference is not SMyyy'
    assert number_of_message_parts == 1, 'number of parts should be 1 '
    assert price_in_millicents_usd >= 0, 'price_in_millicents_usd should be >= 0 '
    assert isinstance(payload, str), 'payload should have been a string'
