import datetime
import pytest
from app.celery.process_delivery_status_result_tasks import (
    _get_provider_info,
    _get_notification_parameters,
    attempt_to_get_notification,
    process_delivery_status,
)
from app.models import Notification
from celery.exceptions import Retry
from tests.app.db import create_notification
from sqlalchemy.sql import text
from sqlalchemy.orm import sessionmaker, Session

from app.dao.notifications_dao import (
    dao_get_notification_by_reference,
    dao_update_notification,
    update_notification_status_by_id,
)

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
def sample_sqs_message_with_provider():
    return {
        "body": "UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV"
                "zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx"
                "MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=",
        "provider": "sms"

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
        sample_sqs_message_with_provider
):
    sample_sqs_message_with_provider['provider'] = 'twilio'

    # now supply the sample to the function we want to test
    provider_name_output, provider = _get_provider_info(MockCeleryTask(), sample_sqs_message_with_provider)

    assert provider.name == 'twilio'
    assert provider_name_output == 'twilio'


def test_attempt_to_get_notification_with_good_data(
        notify_db_session,
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
        reference, notification_status, 0
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
        reference, notification_status, 0
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
        sample_delivery_status_result_message
):
    """Verify that retry is triggered if translate_delivery_status returns None"""

    mocker.patch("app.clients")
    mocker.patch("app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status", return_value=None)

    with pytest.raises(Retry):
        process_delivery_status(event=sample_delivery_status_result_message)


@pytest.mark.parametrize("event_duration_in_seconds", [0, 100, 200, 300, 400])
def test_attempt_to_get_notification_NoResultFound(notify_db_session, event_duration_in_seconds):
    """
    The Celery Task should retry whenever attempt_to_get_notification could not find a matching notification
    and less than 300 seconds (5 minutes) has elapsed since sending the notification.  (This is a race
    condition.)  There won't be a matching notification because this test doesn't create a Notification.
    """

    notification, should_retry, should_exit = attempt_to_get_notification(
        "bad_reference", "delivered", event_duration_in_seconds
    )
    assert notification is None
    assert should_exit

    if event_duration_in_seconds < 300:
        assert should_retry
    else:
        assert not should_retry


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
        sample_template
):
    """Test that celery task will complete if correct data is provided"""

    create_notification(
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


def test_dao_update_notification_will_update_last_updated_without_conditions(
        notify_db_session,
        sample_template,
        notify_db
    ):

    notification_status_delivered = 'delivered'
    reference = 'def'

    # create notification object
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status_delivered
    )

    # get the notification object
    notification = dao_get_notification_by_reference(reference)

    # check the values that attempt_to_get_notification() return against what we sent
    assert isinstance(notification, Notification)
    assert notification.status == notification_status_delivered
    assert notification.reference == reference

    # record the last update value that is in the database
    notification_last_updated = notification.updated_at

    # attempt to do an update of the object
    dao_update_notification(notification)
    notification = dao_get_notification_by_reference(reference)
    assert notification.updated_at > notification_last_updated


def test_notification_cannot_exit_delivered_status(notify_db_session, sample_template, notify_db):
    notification_status_delivered = 'delivered'
    notification_status_sending = 'sending'
    reference = 'abc'

    # create notification object
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status_delivered
    )

    # get the notification object
    notification = dao_get_notification_by_reference(reference)

    # record the last update value that is in the database
    notification_last_updated = notification.updated_at

    # check the values that attempt_to_get_notification() return against what we sent
    assert isinstance(notification, Notification)
    assert notification.status == notification_status_delivered
    assert notification.reference == reference

    # attempt to do an update of the object
    dao_update_notification(notification)
    notification = dao_get_notification_by_reference(reference)
    assert notification.updated_at == notification_last_updated

    # update notification by status id
    update_notification_status_by_id(notification_id=notification.id, status=notification_status_sending)
    notification = dao_get_notification_by_reference(reference)
    assert notification.updated_at == notification_last_updated
    assert notification.status == notification_status_delivered


def test_notification_status_maintain_order(notify_db_session, sample_template, notify_db):
    notification_status_sent = 'sent'
    notification_status_sending = 'sending'
    reference = 'abc'

    # create notification object
    create_notification(
        sample_template,
        reference=reference,
        sent_at=datetime.datetime.utcnow(),
        status=notification_status_sent
    )

    # get the notification object
    notification = dao_get_notification_by_reference(reference)

    # record the last update value that is in the database
    notification_last_updated = notification.updated_at

    # update notification by status id
    update_notification_status_by_id(notification_id=notification.id, status=notification_status_sending)
    notification = dao_get_notification_by_reference(reference)
    assert notification.updated_at == notification_last_updated
    assert notification.status == notification_status_delivered




