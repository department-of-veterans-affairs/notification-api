import pytest
from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from notifications_utils.recipients import InvalidEmailError

import app
from app.celery import provider_tasks
from app.celery.provider_tasks import deliver_sms, deliver_email
from app.clients.email.aws_ses import AwsSesClientException
from app.exceptions import NotificationTechnicalFailureException, InvalidProviderException


def test_should_have_decorated_tasks_functions():
    assert deliver_sms.__wrapped__.__name__ == 'deliver_sms'
    assert deliver_email.__wrapped__.__name__ == 'deliver_email'


def test_should_call_send_sms_to_provider_from_deliver_sms_task(
        sample_notification,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider')

    deliver_sms(sample_notification.id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_sms_task(
        notify_db_session,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider')
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry')

    notification_id = app.create_uuid()

    deliver_sms(notification_id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_sms.retry.assert_called_with(queue="retry-tasks", countdown=0)


def test_should_call_send_email_to_provider_from_deliver_email_task(
        sample_notification,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider')

    deliver_email(sample_notification.id)
    app.delivery.send_to_providers.send_email_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_email_task(mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider')
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    notification_id = app.create_uuid()

    deliver_email(notification_id)
    app.delivery.send_to_providers.send_email_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_email.retry.assert_called_with(queue="retry-tasks")


# DO THESE FOR THE 4 TYPES OF TASK

def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_sms_task(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider', side_effect=Exception("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry', side_effect=MaxRetriesExceededError())

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_sms(sample_notification.id)
    assert str(sample_notification.id) in str(e.value)

    provider_tasks.deliver_sms.retry.assert_called_with(queue="retry-tasks", countdown=0)

    assert sample_notification.status == 'technical-failure'


def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_email_task(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=Exception("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.deliver_email.retry', side_effect=MaxRetriesExceededError())

    with pytest.raises(NotificationTechnicalFailureException) as e:
        deliver_email(sample_notification.id)
    assert str(sample_notification.id) in str(e.value)

    provider_tasks.deliver_email.retry.assert_called_with(queue="retry-tasks")
    assert sample_notification.status == 'technical-failure'


def test_should_technical_error_and_not_retry_if_invalid_email(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=InvalidEmailError('bad email'))
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    with pytest.raises(NotificationTechnicalFailureException):
        deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is False
    assert sample_notification.status == 'technical-failure'


def test_should_technical_error_and_not_retry_if_invalid_provider(sample_notification, mocker):
    mocker.patch(
        'app.delivery.send_to_providers.send_email_to_provider',
        side_effect=InvalidProviderException('invalid provider')
    )
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    with pytest.raises(NotificationTechnicalFailureException):
        deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is False
    assert sample_notification.status == 'technical-failure'


def test_should_retry_and_log_exception(sample_notification, mocker):
    error_response = {
        'Error': {
            'Code': 'SomeError',
            'Message': 'some error message from amazon',
            'Type': 'Sender'
        }
    }
    ex = ClientError(error_response=error_response, operation_name='opname')
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=AwsSesClientException(str(ex)))
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is True
    assert sample_notification.status == 'created'


def test_send_sms_should_not_switch_providers_on_non_provider_failure(
    sample_notification,
    mocker
):
    mocker.patch(
        'app.delivery.send_to_providers.send_sms_to_provider',
        side_effect=Exception("Non Provider Exception")
    )
    switch_provider_mock = mocker.patch('app.delivery.send_to_providers.dao_toggle_sms_provider')
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry')

    deliver_sms(sample_notification.id)

    assert switch_provider_mock.called is False
