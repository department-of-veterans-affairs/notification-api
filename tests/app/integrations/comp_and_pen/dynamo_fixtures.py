import boto3
import pytest
from moto import mock_dynamodb


@pytest.fixture
def dynamodb_mock():
    """
    Mock the DynamoDB table used for the Comp and Pen integration.
    """

    bip_table_vars = {
        'TableName': 'TestTable',
        'AttributeDefinitions': [
            {
                'AttributeName': 'participant_id',
                'AttributeType': 'N',
            },
            {
                'AttributeName': 'payment_id',
                'AttributeType': 'N',
            },
            {
                'AttributeName': 'is_processed',
                'AttributeType': 'S',
            },
        ],
        'KeySchema': [
            {'AttributeName': 'participant_id', 'KeyType': 'HASH'},
            {'AttributeName': 'payment_id', 'KeyType': 'RANGE'},
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'is-processed-index',
                'KeySchema': [{'AttributeName': 'is_processed', 'KeyType': 'HASH'}],
                'Projection': {
                    'ProjectionType': 'ALL',
                },
            },
        ],
        'BillingMode': 'PAY_PER_REQUEST',
    }
    with mock_dynamodb():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

        # Create a mock DynamoDB table
        table = dynamodb.create_table(**bip_table_vars)

        # Wait for table to be created
        table.meta.client.get_waiter('table_exists').wait(TableName='TestTable')

        yield table


@pytest.fixture
def sample_dynamodb_insert(dynamodb_mock):
    items_inserted = []

    def _dynamodb_insert(items_to_insert: list):
        with dynamodb_mock.batch_writer() as batch:
            for item in items_to_insert:
                batch.put_item(Item=item)
                items_inserted.append(item)

    yield _dynamodb_insert

    # delete the items added
    for item in items_inserted:
        dynamodb_mock.delete_item(Key={'participant_id': item['participant_id'], 'payment_id': item['payment_id']})
