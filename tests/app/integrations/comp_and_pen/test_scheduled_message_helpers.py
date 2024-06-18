from decimal import Decimal

import pytest

from app.integrations.comp_and_pen.scheduled_message_helpers import CompPenMsgHelper
from tests.app.celery.test_scheduled_tasks import dynamodb_mock, sample_dynamodb_insert


@pytest.fixture
def msg_helper(mocker) -> CompPenMsgHelper:
    # Mocks necessary for dynamodb
    mocker.patch('boto3.resource')
    mocker.patch('boto3.resource.Table', return_value=dynamodb_mock)
    return CompPenMsgHelper('test')


def test_ut_get_dynamodb_comp_pen_messages_with_empty_table(mocker, msg_helper):
    mocker.patch(
        'app.integrations.comp_and_pen.scheduled_message_helpers.CompPenMsgHelper.get_dynamodb_comp_pen_messages',
        return_value=[],
    )
    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=1)

    assert messages == [], 'Expected no messages from an empty table'


def test_get_dynamodb_comp_pen_messages_filters(mocker, msg_helper, dynamodb_mock, sample_dynamodb_insert):
    """
    Items should not be returned if any of these apply:
        2) has_duplicate_mappings is True
        3) payment_id equals -1
        4) paymentAmount is absent (required by downstream Celery task)
    """
    # Insert mock data into the DynamoDB table.
    items_to_insert = [
        # The first 2 items are valid.
        {'participant_id': 1, 'is_processed': 'F', 'payment_id': 1, 'paymentAmount': Decimal(1.00)},
        {
            'participant_id': 2,
            'is_processed': 'F',
            'has_duplicate_mappings': False,
            'payment_id': 2,
            'paymentAmount': Decimal(2.50),
        },
        # Already processed
        {'participant_id': 4, 'payment_id': 4, 'paymentAmount': Decimal(0)},
        # Duplicate mappings
        {
            'participant_id': 5,
            'is_processed': 'F',
            'has_duplicate_mappings': True,
            'payment_id': 5,
            'paymentAmount': Decimal('0.99'),
        },
        # Placeholder payment_id
        {'participant_id': 6, 'is_processed': 'F', 'payment_id': -1, 'paymentAmount': Decimal(1.00)},
        # Missing paymentAmount
        {'participant_id': 7, 'is_processed': 'F', 'payment_id': 1},
    ]
    sample_dynamodb_insert(items_to_insert)

    # has to attribute 'table'
    # mocker.patch('app.integrations.comp_and_pen.scheduled_message_helpers.CompPenMsgHelper.table', dynamodb_mock)

    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=7)

    for msg in messages:
        assert (
            str(msg['participant_id']) in '12'
        ), f"The message with ID {msg['participant_id']} should have been filtered out."
    assert len(messages) == 2


def test_it_get_dynamodb_comp_pen_messages_with_multiple_scans(
    mocker,
    msg_helper,
    dynamodb_mock,
    sample_dynamodb_insert,
):
    """
    Items should be searched based on the is_processed index and payment_id = -1 should be filtered out.
    """
    # items with is_processed = 'F'
    not_processed_items = [
        {
            'participant_id': x,
            'is_processed': 'F',
            'payment_id': x if x % 5 != 0 else -1,
            'paymentAmount': Decimal(x * 2.50),
            'vaprofile_id': x * 10,
        }
        for x in range(0, 1000, 2)
    ]

    # items with is_processed removed (not in index)
    processed_items = [
        {
            'participant_id': x,
            'payment_id': x if x % 5 != 0 else -1,
            'paymentAmount': Decimal(x * 2.50),
            'vaprofile_id': x * 10,
        }
        for x in range(1, 1001, 2)
    ]

    # Insert mock data into the DynamoDB table.
    sample_dynamodb_insert(processed_items + not_processed_items)

    # mocker.patch.object(msg_helper.table, dynamodb_mock)

    # Invoke the function with the mocked table and application
    messages = msg_helper.get_dynamodb_comp_pen_messages(message_limit=100)

    assert len(messages) == 100

    # ensure we only have messages that have not been processed
    for m in messages:
        assert m['is_processed'] == 'F'
        assert m['payment_id'] != -1


def test_it_update_dynamo_item_is_processed_updates_properly(mocker, msg_helper, dynamodb_mock, sample_dynamodb_insert):
    items_to_insert = [
        {'participant_id': 1, 'is_processed': 'F', 'payment_id': 1, 'paymentAmount': Decimal(1.00)},
        {'participant_id': 2, 'is_processed': 'F', 'payment_id': 2, 'paymentAmount': Decimal(2.50)},
        {'participant_id': 3, 'payment_id': 1, 'paymentAmount': Decimal(0.00)},
    ]

    # Insert mock data into the DynamoDB table.
    sample_dynamodb_insert(items_to_insert)

    # mocker.patch.object(msg_helper.table, dynamodb_mock)

    msg_helper.remove_dynamo_item_is_processed(items_to_insert)

    response = dynamodb_mock.scan()

    # Ensure we get all 3 records back and they are set with is_processed removed
    assert response['Count'] == 3
    for item in response['Items']:
        assert 'is_processed' not in item
