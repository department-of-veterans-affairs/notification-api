import datetime
import json
import pytest
from app.celery import process_delivery_status_result_tasks
from app.dao import notifications_dao
from app.feature_flags import FeatureFlag
from tests.app.db import create_notification
from celery.exceptions import Retry
from app.dao.service_callback_api_dao import (save_service_callback_api)
from app.models import ServiceCallback, WEBHOOK_CHANNEL_TYPE, NOTIFICATION_SENT, DELIVERY_STATUS_CALLBACK_TYPE


# confirm that sqs task will not run when sqs messaging is disabled
def test_passes_if_toggle_disabled(mocker, db_session):
    # set is_feature_enabled = False
    mock_toggle = mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=False)

    mock_dao_get_notification_by_reference = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.dao_get_notification_by_reference'
    )
    mock_update_notification_status_by_id = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.update_notification_status_by_id'
    )

    # Call process_delivery status with an empty event
    process_delivery_status_result_tasks.process_delivery_status(event={})

    # confirm that is_feature_event() was called using the FeatureFlag property
    mock_toggle.assert_called_with(FeatureFlag.PROCESS_DELIVERY_STATUS_ENABLED)

    #  confirm that dao_get_notification_by_reference() was never called
    mock_dao_get_notification_by_reference.assert_not_called()

    # confirm that update_notification_status_by_id was never called
    mock_update_notification_status_by_id.assert_not_called()


# test that celery will start processing event when sqs messaging is enabled
def test_create_notification(mocker, db_session, sample_template):
    # make sure process delivery status results enabled
    mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)

    # create a notification
    test_reference = 'sms-reference-1'
    create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
    notification = notifications_dao.dao_get_notification_by_reference(test_reference)
    assert notification.status == 'sending'


# we want to test that celery task will retry when invalid provider is given
def test_retry_with_invalid_provider_name(mocker, db_session, sample_template):
    process_delivery_status_result_task_message = {
        "provider": 't',
        "body": {
            "payload": "Hello! 👍",
            "reference": 'sms-reference-1',
            "record_status": 'delivered',
            "number_of_message_parts": 0,
            "price_in_millicents_usd": 0
        }
    }
    message = {'Message': bytes(json.dumps(process_delivery_status_result_task_message), 'utf-8')}

    # make sure process delivery status results enabled
    mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)

    # create a notification
    test_reference = 'sms-reference-1'
    create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
    with pytest.raises(Retry):
        process_delivery_status_result_tasks.process_delivery_status(event=message)


# we want to test that celery task will fail when invalid provider is given
def test_with_correct_provider_name(mocker, db_session, sample_template, sample_service):
    test_reference = 'sms-reference-1'
    process_delivery_status_result_task_message = {
        "provider": 'twilio',
        "body": {
            "payload": "Hello! 👍",
            "reference": test_reference,
            "record_status": 'delivered',
            "number_of_message_parts": 1,
            "price_in_millicents_usd": 0
        }
    }
    message = {'Message': bytes(json.dumps(process_delivery_status_result_task_message), 'utf-8')}

    # make sure process delivery status results enabled
    mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)

    # create a notification
    create_notification(
        template=sample_template, reference=test_reference,
        sent_at=datetime.datetime.utcnow(), status='sending'
    )

    process_delivery_status_result_tasks.process_delivery_status(event=message)
    assert True
