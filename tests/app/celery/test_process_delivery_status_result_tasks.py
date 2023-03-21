import datetime
import json

from app.celery import process_delivery_status_result_tasks
from app.dao import notifications_dao
from app.feature_flags import FeatureFlag
from tests.app.db import create_notification


# db session variable is required parameter even though it is not used
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


def test_create_notification(mocker, db_session, sample_template):
    # make sure process delivery status results enabled
    mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)

    # create a notification
    test_reference = 'sms-reference-1'
    create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
    notification = notifications_dao.dao_get_notification_by_reference(test_reference)
    assert notification.status == 'sending'


def test_event_message(mocker, db_session, sample_template):
    # make sure process delivery status results enabled
    mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)
    mock_dao_get_notification_by_reference = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.dao_get_notification_by_reference'
    )
    # create a notification
    test_reference = 'sms-reference-1'
    create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
    process_delivery_status_result_tasks.process_delivery_status(
        event=pdsr_notification_callback_record(
            reference='reference-1',
            provider='twilio',
            record_status='DELIVERED'
        )
    )


def pdsr_notification_callback_record(
        reference,
        provider='twilio',
        record_status='delivered',
):
    process_delivery_status_result_task_message = {
        "provider": provider,
        "body": {
            "payload": "Hello! 👍",
            "reference": reference,
            "record_status": record_status,
            "number_of_message_parts": 0,
            "price_in_millicents_usd": 0
        }
    }

    return {
        'Message':
            bytes(json.dumps(process_delivery_status_result_task_message), 'utf-8')

    }
