from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.integrations.comp_and_pen.scheduled_message_helpers import CompPenMsgHelper
from app.models import SMS_TYPE
from app.va.identifier import IdentifierType


@pytest.fixture
def msg_helper(mocker, dynamodb_mock) -> CompPenMsgHelper:
    # Mocks necessary for dynamodb
    mocker.patch('boto3.resource')
    helper = CompPenMsgHelper('test')
    mocker.patch.object(helper, 'dynamodb_table', dynamodb_mock)
    return helper


def test_ut_get_dynamodb_comp_pen_messages_with_empty_table(msg_helper):
    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=1)

    assert messages == [], 'Expected no messages from an empty table'


def test_get_dynamodb_comp_pen_messages_filters(msg_helper, sample_dynamodb_insert):
    """
    Items should not be returned if any of these apply:
        1) payment_id equals -1
        2) paymentAmount is absent (required by downstream Celery task)
    """
    # Insert mock data into the DynamoDB table.
    items_to_insert = [
        # The first 3 items are valid.
        {'participant_id': 1, 'is_processed': 'F', 'payment_id': 1, 'paymentAmount': Decimal(1.00), 'vaprofile_id': 1},
        {'participant_id': 2, 'is_processed': 'F', 'payment_id': 2, 'paymentAmount': Decimal(2.50), 'vaprofile_id': 2},
        {'participant_id': 3, 'is_processed': 'F', 'payment_id': 3, 'paymentAmount': Decimal('3.9'), 'vaprofile_id': 3},
        # Already processed
        {'participant_id': 4, 'payment_id': 4, 'paymentAmount': Decimal(0), 'vaprofile_id': 4},
        # Missing paymentAmount
        {'participant_id': 5, 'is_processed': 'F', 'payment_id': 5, 'vaprofile_id': 5},
        # Placeholder payment_id
        {'participant_id': 6, 'is_processed': 'F', 'payment_id': -1, 'paymentAmount': Decimal(1.00), 'vaprofile_id': 6},
    ]
    sample_dynamodb_insert(items_to_insert)

    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=7)

    for msg in messages:
        assert (
            str(msg['participant_id']) in '123'
        ), f"The message with ID {msg['participant_id']} should have been filtered out."
    assert len(messages) == 3


def test_it_get_dynamodb_comp_pen_messages_with_multiple_scans(msg_helper, sample_dynamodb_insert):
    """
    Items should be searched based on the is-processed-index and payment_id = -1 should be filtered out.

    This is also testing the pagination of the scan operation in which a bug previously existed.
    """
    items_to_insert = (
        # items with is_processed = 'F'
        {
            'participant_id': x,
            'is_processed': 'F',
            'payment_id': x,
            'paymentAmount': Decimal(x * 2.50),
            'vaprofile_id': x * 10,
        }
        if x % 2 == 0
        # items with is_processed removed (not in index)
        else {
            'participant_id': x,
            'payment_id': x,
            'paymentAmount': Decimal(x * 2.50),
            'vaprofile_id': x * 10,
        }
        for x in range(0, 250)
    )

    # Insert mock data into the DynamoDB table.
    sample_dynamodb_insert(items_to_insert)

    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=100)

    assert len(messages) == 100

    # ensure we only have messages that have not been processed
    for m in messages:
        assert m['is_processed'] == 'F'
        assert m['payment_id'] != -1


def test_it_update_dynamo_item_is_processed_updates_properly(mocker, msg_helper, dynamodb_mock, sample_dynamodb_insert):
    """Ensure that the 'is_processed' key is removed from the items in the list and the DynamoDB table is updated."""

    items_to_insert = [
        {'participant_id': 1, 'is_processed': 'F', 'payment_id': 1, 'paymentAmount': Decimal(1.00)},
        {'participant_id': 2, 'is_processed': 'F', 'payment_id': 2, 'paymentAmount': Decimal(2.50)},
        {'participant_id': 3, 'payment_id': 1, 'paymentAmount': Decimal(0.00)},
        {'participant_id': 4, 'is_processed': 'F', 'payment_id': 2, 'paymentAmount': Decimal(4.50)},
        {'participant_id': 5, 'is_processed': 'F', 'payment_id': 1, 'paymentAmount': Decimal(5.50)},
    ]

    # Insert mock data into the DynamoDB table.
    sample_dynamodb_insert(items_to_insert)

    mock_logger = mocker.patch('app.integrations.comp_and_pen.scheduled_message_helpers.current_app.logger')

    # why is this giving this error? "RuntimeError: Working outside of application context."
    msg_helper.remove_dynamo_item_is_processed(items_to_insert)

    mock_logger.info.assert_called()

    response = dynamodb_mock.scan()

    # Ensure we get all 5 records back and they are set with is_processed removed
    assert response['Count'] == 5
    for item in response['Items']:
        assert 'is_processed' not in item


# is this really necessary? The above test removed item values and uses batch write to update them
# def test_send_scheduled_comp_and_pen_sms_uses_batch_write(mocker, sample_service, sample_template):
#     # mocker.patch('app.celery.scheduled_tasks.send_notification_bypass_route')

#     # mocker.patch('app.celery.scheduled_tasks.dao_fetch_service_by_id', return_value=sample_service)
#     # template = sample_template()
#     # mocker.patch('app.celery.scheduled_tasks.dao_get_template_by_id', return_value=template)

#     dynamo_data = [
#         {
#             'participant_id': '123',
#             'vaprofile_id': '123',
#             'payment_id': '123',
#             'paymentAmount': 123,
#             'is_processed': False,
#         },
#     ]
#     # mocker.patch('app.celery.scheduled_tasks.CompPenMsgHelper.get_dynamodb_comp_pen_messages', return_value=dynamo_data)
#     # mocker.patch.dict('app.celery.scheduled_tasks.current_app.config', {'COMP_AND_PEN_SMS_SENDER_ID': ''})

#     with mocker.patch('app.integrations.comp_and_pen.scheduled_message_helpers.boto3.resource') as mock_resource:
#         mock_put_item = MagicMock()
#         mock_resource.return_value.Table.return_value.batch_writer.return_value.__enter__.return_value.put_item = (
#             mock_put_item
#         )
#         msg_helper = CompPenMsgHelper('test')
#         msg_helper.get_dynamodb_comp_pen_messages(dynamo_data)

#     dynamo_data[0].pop('is_processed', None)
#     mock_put_item.assert_called_once_with(Item=dynamo_data[0])


def test_ut_send_scheduled_comp_and_pen_sms_calls_send_notification_with_recipient_item(
    mocker, msg_helper, dynamodb_mock, sample_service, sample_template
):
    # Set up test data
    dynamo_data = [
        {
            'participant_id': '123',
            'vaprofile_id': '123',
            'payment_id': '123',
            'paymentAmount': 123,
            'is_processed': False,
        },
    ]

    recipient_item = {'id_type': IdentifierType.VA_PROFILE_ID.value, 'id_value': '123'}

    mocker.patch('app.celery.scheduled_tasks.is_feature_enabled', return_value=True)

    service = sample_service()
    template = sample_template()
    sms_sender_id = str(service.get_default_sms_sender_id())

    mock_send_notification = mocker.patch(
        'app.integrations.comp_and_pen.scheduled_message_helpers.send_notification_bypass_route'
    )

    msg_helper.send_scheduled_sms(
        service=service,
        template=template,
        sms_sender_id=sms_sender_id,
        comp_and_pen_messages=dynamo_data,
        perf_to_number=None,
    )

    # Assert the expected information is passed to "send_notification_bypass_route"
    mock_send_notification.assert_called_once_with(
        service=service,
        template=template,
        notification_type=SMS_TYPE,
        personalisation={'paymentAmount': '123'},
        sms_sender_id=sms_sender_id,
        recipient=None,
        recipient_item=recipient_item,
    )
