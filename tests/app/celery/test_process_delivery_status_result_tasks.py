import datetime
from uuid import uuid4

import pytest

from app.celery.exceptions import AutoRetryException
from app.celery.process_delivery_status_result_tasks import (
    _get_provider_info,
    attempt_to_get_notification,
    process_delivery_status,
)
from app.models import Notification, NOTIFICATION_DELIVERED, NOTIFICATION_SENT


@pytest.fixture
def sample_delivery_status_result_message():
    return {
        'message': {
            'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHV'
            'zPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZ'
            'NZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIxMjIyMzMzNDQ0NCZB'
            'cGlWZXJzaW9uPTIwMTAtMDQtMDE=',
            'provider': 'twilio',
        }
    }


@pytest.fixture()
def sample_notification_platform_status():
    return {
        'payload': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHVzPWR'
        'lbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNaGFyZGNvZGVkS1dNJkFjY291bnRTaWQ9QUN6enomRnJvbT'
        '0lMkIxMjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=',
        'reference': 'SMhardcodedKWM',
        'record_status': NOTIFICATION_DELIVERED,
    }


@pytest.fixture()
def sample_sqs_message_with_provider():
    return {
        'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV'
        'zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx'
        'MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=',
        'provider': 'sms',
    }


@pytest.fixture()
def sample_sqs_message_without_provider():
    return {
        'body': 'UmF3RGxyRG9uZURhdGU9MjMwMzIyMjMzOCZTbXNTaWQ9U014eHgmU21zU3RhdHVzPWRlbGl2ZXJlZCZNZXNzYWdlU3RhdHV'
        'zPWRlbGl2ZXJlZCZUbz0lMkIxMTExMTExMTExMSZNZXNzYWdlU2lkPVNNeXl5JkFjY291bnRTaWQ9QUN6enomRnJvbT0lMkIx'
        'MjIyMzMzNDQ0NCZBcGlWZXJzaW9uPTIwMTAtMDQtMDE='
    }


def test_celery_retry_event_when_missing_message_attribute(sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message['message']
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_celery_event_with_missing_provider_attribute(sample_delivery_status_result_message):
    """Test that celery will retry the task if "provider" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message['message']['provider']
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_celery_event_with_missing_body_attribute(sample_delivery_status_result_message):
    """Test that celery will retry the task if "body" is missing from the CeleryEvent message"""

    del sample_delivery_status_result_message['message']['body']
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_celery_event_with_invalid_provider_attribute(sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is invalid from the CeleryEvent message"""

    sample_delivery_status_result_message['message']['provider'] = 'abc123'
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_celery_event_with_invalid_body_attribute(sample_delivery_status_result_message):
    """Test that celery will retry the task if "message" is missing from the CeleryEvent message"""

    sample_delivery_status_result_message['message']['body'] = 'body'
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_get_provider_info_with_no_provider_retries(notify_api, sample_sqs_message_without_provider):
    """Test get_provider_info() retries when no provider is given by the celery event"""

    with pytest.raises(Exception) as exc_info:
        _get_provider_info(sample_sqs_message_without_provider)
    assert exc_info.type is AutoRetryException


def test_get_provider_info_with_invalid_provider_retries(notify_api, sample_sqs_message_with_provider):
    """Test that _get_provider_info() will raise a celery retry when sqs message has an invalid provider"""

    sample_sqs_message_with_provider['provider'] = 'abc'

    # now supply the sample to the function we want to test with the expectation of failure
    with pytest.raises(Exception) as exc_info:
        _get_provider_info(sample_sqs_message_with_provider)
    assert exc_info.type is AutoRetryException


def test_get_provider_info_with_twilio(notify_api, sample_sqs_message_with_provider):
    sample_sqs_message_with_provider['provider'] = 'twilio'

    # now supply the sample to the function we want to test
    provider_name_output, provider = _get_provider_info(sample_sqs_message_with_provider)

    assert provider.name == 'twilio'
    assert provider_name_output == 'twilio'


def test_attempt_to_get_notification_with_good_data(sample_template, sample_notification):
    """Test that we will exit the celery task when sqs message matches what has already been reported in the database"""

    notification_status = NOTIFICATION_DELIVERED
    reference = str(uuid4())

    sample_notification(
        template=sample_template(), reference=reference, sent_at=datetime.datetime.utcnow(), status=notification_status
    )

    notification, should_exit = attempt_to_get_notification(reference, notification_status, 0)

    assert isinstance(notification, Notification)
    assert notification.status == notification_status
    assert notification.reference == reference

    # SQS callback received matches the data in the database, so we should exit the celery task
    assert should_exit


def test_attempt_to_get_notification_duplicate_notification(
    sample_template,
    sample_notification,
):
    """Test that duplicate notifications will make notification = None, should_exit=True"""

    template = sample_template()
    notification_status = NOTIFICATION_DELIVERED
    reference = str(uuid4())

    sample_notification(
        template=template, reference=reference, sent_at=datetime.datetime.utcnow(), status=notification_status
    )

    sample_notification(
        template=template, reference=reference, sent_at=datetime.datetime.utcnow(), status=notification_status
    )

    # should trigger a "MultipleResultsFound" when we attempt to get the notification object
    notification, should_exit = attempt_to_get_notification(reference, notification_status, 0)

    # Remember: celery task will trigger a retry when notification = None
    assert notification is None

    # should_exit=True because of the "MultipleResultsFound" exception
    assert should_exit


@pytest.mark.serial
def test_process_delivery_status_with_invalid_notification_retries(sample_delivery_status_result_message):
    """Notification is invalid because there are no notifications in the database"""
    with pytest.raises(Exception) as exc_info:
        # Fixture is base64 encoded and uses reference: SMyyy, refernces cannot be hard-coded for non-serial tests
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


def test_none_notification_platform_status_triggers_retry(mocker, sample_delivery_status_result_message):
    """Verify that retry is triggered if translate_delivery_status returns None"""

    mocker.patch('app.clients')
    mocker.patch('app.clients.sms.twilio.TwilioSMSClient.translate_delivery_status', return_value=None)

    with pytest.raises(Exception) as exc_info:
        # Fixture is base64 encoded and uses reference: SMyyy, refernces cannot be hard-coded for non-serial tests
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


@pytest.mark.parametrize('event_duration_in_seconds', [-1, 0, 299, 300])
def test_attempt_to_get_notification_NoResultFound(notify_api, event_duration_in_seconds):
    """
    The Celery Task should retry whenever attempt_to_get_notification could not find a matching notification
    and less than 300 seconds (5 minutes) has elapsed since sending the notification.  (This is a race
    condition.)  There won't be a matching notification because this test doesn't create a Notification.
    """

    if event_duration_in_seconds < 300:
        with pytest.raises(Exception) as exc_info:
            # Ignore the returns, we are expecting an exception
            attempt_to_get_notification('bad_reference', NOTIFICATION_DELIVERED, event_duration_in_seconds)
        assert exc_info.type is AutoRetryException
    else:
        notification, should_exit = attempt_to_get_notification(
            'bad_reference', NOTIFICATION_DELIVERED, event_duration_in_seconds
        )
        assert notification is None
        assert should_exit


def test_process_delivery_status_should_retry_preempts_exit(sample_delivery_status_result_message):
    with pytest.raises(Exception) as exc_info:
        process_delivery_status(event=sample_delivery_status_result_message)
    assert exc_info.type is AutoRetryException


@pytest.mark.serial
def test_process_delivery_status_with_valid_message_with_no_payload(
    mocker,
    sample_delivery_status_result_message,
    sample_template,
    sample_notification,
):
    """
    Test that the Celery task will complete if correct data is provided.
    """

    # This test is marked "serial" because the reference is used by many tests.  Making it a random
    # value causes the test to fail.
    notification = sample_notification(
        template=sample_template(), reference='SMyyy', sent_at=datetime.datetime.utcnow(), status=NOTIFICATION_SENT
    )

    callback_mock = mocker.patch('app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task')
    assert process_delivery_status(event=sample_delivery_status_result_message)

    assert callback_mock.call_args.args[0].id == notification.id
    assert callback_mock.call_args.args[1] == {}


@pytest.mark.serial
def test_process_delivery_status_with_valid_message_with_payload(
    mocker,
    sample_delivery_status_result_message,
    sample_template,
    sample_notification,
):
    """
    Test that the Celery task will complete if correct data is provided.
    """

    # This test is marked "serial" because the reference is used by many tests.  Making it a random
    # value causes the test to fail.
    sample_notification(
        template=sample_template(), reference='SMyyy', sent_at=datetime.datetime.utcnow(), status=NOTIFICATION_SENT
    )

    mocker.patch('app.celery.process_delivery_status_result_tasks._get_include_payload_status', returns=True)
    callback_mock = mocker.patch('app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task')
    assert process_delivery_status(event=sample_delivery_status_result_message)
    callback_mock.assert_called_once()


@pytest.mark.serial
def test_wt_delivery_status_callback_should_log_total_time(
    mocker,
    client,
    sample_template,
    sample_notification,
    sample_delivery_status_result_message,
):
    mock_log_total_time = mocker.patch('app.celery.common.log_notification_total_time')
    mocker.patch('app.celery.service_callback_tasks.check_and_queue_callback_task')

    notification = sample_notification(template=sample_template(), status=NOTIFICATION_SENT, reference='SMyyy')
    # Mock db call
    mocker.patch(
        'app.dao.notifications_dao.dao_get_notification_by_reference',
        return_value=notification,
    )

    # Reference is used by many tests, can lead to trouble
    process_delivery_status(event=sample_delivery_status_result_message)

    assert mock_log_total_time.called_once_with(
        notification.id,
        notification.created_at,
        NOTIFICATION_DELIVERED,
        'twilio',
    )


@pytest.mark.serial
def test_process_delivery_status_no_status_reason_for_delivered(
    notify_db_session,
    mocker,
    sample_template,
    sample_notification,
    sample_delivery_status_result_message,
):
    """
    When a notification is updated to "delivered" status, its "status_reason" should be set to
    the empty string.
    """

    # This test is marked "serial" because the reference is used by many tests.  Making it a random
    # value causes the test to fail.
    notification = sample_notification(
        template=sample_template(),
        reference='SMyyy',
        sent_at=datetime.datetime.utcnow(),
        status=NOTIFICATION_SENT,
        status_reason='This is not the empty string.',
    )
    assert notification.reference == 'SMyyy'
    assert notification.status == NOTIFICATION_SENT
    assert notification.status_reason

    mocker.patch('app.celery.process_delivery_status_result_tasks._get_include_payload_status', returns=True)
    callback_mock = mocker.patch('app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task')

    assert process_delivery_status(event=sample_delivery_status_result_message)
    callback_mock.assert_called_once()

    notify_db_session.session.refresh(notification)
    assert notification.reference == 'SMyyy'
    assert notification.status == NOTIFICATION_DELIVERED
    assert notification.status_reason is None
