import base64
import datetime
import json

from app.celery import process_delivery_status_result_tasks
from app.dao import notifications_dao
from app.feature_flags import FeatureFlag
from tests.app.db import create_notification


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
    mock_dao_get_notification_by_reference = mocker.patch(
        'app.celery.process_delivery_status_result_tasks.dao_get_notification_by_reference'
    )
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
    notification = notifications_dao.dao_get_notification_by_reference(test_reference)

    process_delivery_status_result_tasks.process_delivery_status(
        event=pdsr_notification_callback_record(
            reference=test_reference,
            event_type='_SMS.SUCCESS',
            record_status='DELIVERED'
        )
    )

# def test_callback_task(mocker, db_session, sample_template, event_type, record_status):
#
#     # make sure process delivery status results enabled
#     mock_toggle = mocker.patch('app.celery.process_delivery_status_result_tasks.is_feature_enabled', return_value=True)
#     mock_callback = mocker.patch('app.celery.process_delivery_status_result_tasks.check_and_queue_callback_task')
#
#     # create a notification
#     test_reference = 'sms-reference-1'
#     create_notification(sample_template, reference=test_reference, sent_at=datetime.datetime.utcnow(), status='sending')
#     process_delivery_status_result_tasks.process_delivery_status(
#         event=pdsr_notification_callback_record(
#             reference=test_reference, event_type=event_type, record_status=record_status
#         )
#     )
#
#     notification = notifications_dao.dao_get_notification_by_reference(test_reference)
#     assert notification.status == expected_notification_status
#     mock_callback.assert_called_once()


def pdsr_notification_callback_record(
        reference,
        event_type='_SMS.SUCCESS',
        record_status='DELIVERED'
):
    process_delivery_status_result_task_message = {
        "provider": "twilio",
        "account_sid": "TWILIO_TEST_ACCOUNT_SID_XXX",
        "api_version": "2010-04-01",
        "body": "Hello! 👍",
        "date_created": "Thu, 30 Jul 2015 20:12:31 +0000",
        "date_sent": "Thu, 30 Jul 2015 20:12:33 +0000",
        "date_updated": "Thu, 30 Jul 2015 20:12:33 +0000",
        "direction": "outbound-api",
        "error_code": None,
        "error_message": None,
        "from": "+18194120710",
        "messaging_service_sid": "MGXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "num_media": "0",
        "num_segments": "1",
        "price": -0.00750,
        "price_unit": "USD",
        "sid": "MMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "status": "sent",
        "subresource_uris": {
            "media": "/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages"
                     "/SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/Media.json"
        },
        "to": "+14155552345",
        "uri": "/2010-04-01/Accounts/TWILIO_TEST_ACCOUNT_SID_XXX/Messages/SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.json",
    }

    return {
        'Message':
            bytes(json.dumps(process_delivery_status_result_task_message), 'utf-8')

    }
