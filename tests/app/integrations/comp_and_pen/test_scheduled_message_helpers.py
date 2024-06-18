from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.integrations.comp_and_pen.scheduled_message_helpers import CompPenMsgHelper
from app.va.identifier import IdentifierType
# from tests.app.celery.test_scheduled_tasks import dynamodb_mock, sample_dynamodb_insert


@pytest.fixture
def msg_helper(mocker, dynamodb_mock) -> CompPenMsgHelper:
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


def test_send_scheduled_comp_and_pen_sms_uses_batch_write(mocker, msg_helper, sample_service, sample_template):
    # mocker.patch('app.celery.scheduled_tasks.send_notification_bypass_route')

    # mocker.patch('app.celery.scheduled_tasks.dao_fetch_service_by_id', return_value=sample_service)
    # template = sample_template()
    # mocker.patch('app.celery.scheduled_tasks.dao_get_template_by_id', return_value=template)

    dynamo_data = [
        {
            'participant_id': '123',
            'vaprofile_id': '123',
            'payment_id': '123',
            'paymentAmount': 123,
            'is_processed': False,
        },
    ]
    # mocker.patch('app.celery.scheduled_tasks.CompPenMsgHelper.get_dynamodb_comp_pen_messages', return_value=dynamo_data)
    # mocker.patch.dict('app.celery.scheduled_tasks.current_app.config', {'COMP_AND_PEN_SMS_SENDER_ID': ''})

    with mocker.patch('app.integrations.comp_and_pen.scheduled_message_helpers.boto3.resource') as mock_resource:
        mock_put_item = MagicMock()
        mock_resource.return_value.Table.return_value.batch_writer.return_value.__enter__.return_value.put_item = (
            mock_put_item
        )

        msg_helper.get_dynamodb_comp_pen_messages(dynamo_data)

    dynamo_data[0].pop('is_processed', None)
    mock_put_item.assert_called_once_with(Item=dynamo_data[0])


def test_ut_send_scheduled_comp_and_pen_sms_calls_send_notification_with_recipient_item(
    mocker, dynamodb_mock, sample_service, sample_template
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

    # Mocks necessary for dynamodb
    mocker.patch('boto3.resource')
    mocker.patch('boto3.resource.Table', return_value=dynamodb_mock)

    # Mock the various functions called
    mock_get_dynamodb_messages = mocker.patch(
        'app.celery.scheduled_tasks.CompPenMsgHelper.get_dynamodb_comp_pen_messages', return_value=dynamo_data
    )
    # mock_fetch_service = mocker.patch(
    #     'app.celery.scheduled_tasks.dao_fetch_service_by_id', return_value=sample_service_sms_permission
    # )
    template = sample_template()
    # mock_get_template = mocker.patch('app.celery.scheduled_tasks.dao_get_template_by_id', return_value=template)

    mocker.patch(
        'app.celery.scheduled_tasks.lookup_notification_sms_setup_data',
        return_value=(
            sample_service,
            template,
            sample_service.get_default_sms_sender_id(),
        ),
    )

    mock_send_notification = mocker.patch('app.celery.scheduled_tasks.CompPenMsgHelper.send_scheduled_sms')
    mocker.patch.dict('app.celery.scheduled_tasks.current_app.config', {'COMP_AND_PEN_SMS_SENDER_ID': ''})

    send_scheduled_comp_and_pen_sms()

    # Assert the functions are being called that should be
    mock_get_dynamodb_messages.assert_called_once()
    # mock_fetch_service.assert_called_once()
    # mock_get_template.assert_called_once()

    # Assert the expected information is passed to "send_notification_bypass_route"
    # mock_send_notification.assert_called_once_with(
    #     service=sample_service_sms_permission,
    #     template=template,
    #     notification_type=SMS_TYPE,
    #     personalisation={'paymentAmount': '123'},
    #     sms_sender_id=sample_service_sms_permission.get_default_sms_sender_id(),
    #     recipient=None,
    #     recipient_item=recipient_item,
    # )
    mock_send_notification.assert_called_once_with(
        service=sample_service,
        template=template,
        sms_sender_id=sample_service.get_default_sms_sender_id(),
        comp_and_pen_messages=dynamo_data,
        perf_to_number=None,
    )