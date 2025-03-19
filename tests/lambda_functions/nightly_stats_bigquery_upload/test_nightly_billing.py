import csv
from io import StringIO
import json

import boto3
import pytest
from google.auth.credentials import Credentials
from google.cloud.bigquery import Client
from moto import mock_aws

import lambda_functions.nightly_stats_bigquery_upload.nightly_stats_bigquery_upload_lambda as nightly_lambda

AWS_REGION = 'us-gov-west-1'
BUCKET_NAME = 'my_stats_bucket'
BQ_TABLE_ID = 'test_table_id'
OBJECT_KEY_STATS = '2021-06-28.stats.csv'
OBJECT_KEY_BILLING = '2021-06-28.billing.csv'

# from https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html
EXAMPLE_S3_EVENT_STATS = {
    'Records': [
        {
            'eventVersion': '2.2',
            'eventSource': 'aws:s3',
            'awsRegion': AWS_REGION,
            'eventTime': '1970-01-01T00:00:00.000Z',
            'eventName': 'ObjectCreated:Put',
            'userIdentity': {'principalId': 'AIDAJDPLRKLG7UEXAMPLE'},
            'requestParameters': {'sourceIPAddress': '127.0.0.1'},
            'responseElements': {
                'x-amz-request-id': 'C3D13FE58DE4C810',
                'x-amz-id-2': 'FMyUVURIY8/IgAtTv8xRjskZQpcIZ9KG4V5Wp6S7S/JRWeUWerMUE5JgHvANOjpD',
            },
            's3': {
                's3SchemaVersion': '1.0',
                'configurationId': 'testConfigRule',
                'bucket': {
                    'name': BUCKET_NAME,
                    'ownerIdentity': {'principalId': 'A3NL1KOZZKExample'},
                    'arn': f'arn:aws:s3:::{BUCKET_NAME}',
                },
                'object': {
                    'key': OBJECT_KEY_STATS,
                    'size': 1024,
                    'eTag': 'd41d8cd98f00b204e9800998ecf8427e',
                    'versionId': '096fKKXTRTtl3on89fVO.nfljtsv6qko',
                    'sequencer': '0055AED6DCD90281E5',
                },
            },
        }
    ]
}

EXAMPLE_S3_EVENT_BILLING = EXAMPLE_S3_EVENT_STATS.copy()
EXAMPLE_S3_EVENT_BILLING['Records'][0]['s3']['object']['key'] = OBJECT_KEY_BILLING

EXAMPLE_SERVICE_ACCOUNT_INFO = {
    'type': 'service_account',
    'private_key': 'foo',
    'client_email': 'some email',
    'token_uri': 'some uri',
}

EXAMPLE_NIGHTLY_STATS_LIST = [
    ['service id', 'service name', 'template id', 'template name', 'status', 'count', 'channel_type'],
    ['some service id', 'some service name', 'some template id', 'some template name', 'some status', '5', 'email'],
    ['other service id', 'other service name', 'other template id', 'other template name', 'other status', '5', 'sms'],
]

EXAMPLE_NIGHTLY_BILLING_LIST = [
    [
        'service_name',
        'service_id',
        'template_name',
        'template_id',
        'sender',
        'sender_id',
        'billing_code',
        'count',
        'channel_type',
        'total_message_parts',
        'total_cost',
    ],
    [
        'some service name',
        'some service id',
        'some template name',
        'some template id',
        'some sender',
        'some sender id',
        'some billing code',
        '4',
        'sms',
        '9',
        '753.1',
    ],
    [
        'other service name',
        'other service id',
        'other template name',
        'other template id',
        'other sender',
        'other sender id',
        'other billing code',
        '5',
        'sms',
        '5',
        '555.4',
    ],
]


def example_nightly_stats_bytes() -> bytes:
    nightly_stats_buffer = StringIO()
    writer = csv.writer(nightly_stats_buffer)
    writer.writerows(EXAMPLE_NIGHTLY_STATS_LIST)
    return nightly_stats_buffer.getvalue().encode()


def example_nightly_billing_bytes() -> bytes:
    nightly_billing_buffer = StringIO()
    writer = csv.writer(nightly_billing_buffer)
    writer.writerows(EXAMPLE_NIGHTLY_BILLING_LIST)
    return nightly_billing_buffer.getvalue().encode()


@pytest.fixture(scope='module')
def mock_s3_client():
    with mock_aws():
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        s3_client.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={'LocationConstraint': AWS_REGION},
        )

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=OBJECT_KEY_STATS,
            Body=example_nightly_stats_bytes(),
        )

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=OBJECT_KEY_BILLING,
            Body=example_nightly_billing_bytes(),
        )

        yield s3_client

        s3_client.delete_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY_BILLING)
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY_STATS)
        s3_client.delete_bucket(Bucket=BUCKET_NAME)


@pytest.fixture(scope='module')
def mock_ssm_client():
    with mock_aws():
        ssm_client = boto3.client('ssm', region_name=AWS_REGION)
        ssm_client.put_parameter(
            Name='/bigquery/credentials',
            Value=json.dumps(EXAMPLE_SERVICE_ACCOUNT_INFO),
            Type='SecureString',
        )

        yield ssm_client

        ssm_client.delete_parameter(Name='/bigquery/credentials')


@pytest.fixture
def mock_bigquery_client(mocker):
    mock_bigquery = mocker.patch(
        'lambda_functions.nightly_stats_bigquery_upload.nightly_stats_bigquery_upload_lambda.bigquery'
    )

    mock_client = mocker.Mock(Client)
    mock_bigquery.Client.return_value = mock_client

    return mock_client


@pytest.fixture(autouse=True)
def mock_credentials(mocker):
    mock_service_account = mocker.patch(
        'lambda_functions.nightly_stats_bigquery_upload.nightly_stats_bigquery_upload_lambda.service_account'
    )

    mock_service_account.Credentials.from_service_account_info.return_value = mocker.Mock(Credentials)


def test_read_service_account_info_from_ssm(mock_ssm_client) -> None:
    assert nightly_lambda.read_service_account_info_from_ssm() == EXAMPLE_SERVICE_ACCOUNT_INFO


def test_get_object_key():
    assert nightly_lambda.get_object_key(EXAMPLE_S3_EVENT_STATS) == OBJECT_KEY_STATS


def test_get_bucket_name():
    assert nightly_lambda.get_bucket_name(EXAMPLE_S3_EVENT_STATS) == BUCKET_NAME


@pytest.mark.parametrize(
    'object_key, expected_response',
    [
        (OBJECT_KEY_STATS, example_nightly_stats_bytes()),
        (OBJECT_KEY_BILLING, example_nightly_billing_bytes()),
    ],
    ids=['stats', 'billing'],
)
def test_read_nightly_stats_from_s3(mock_s3_client, object_key, expected_response) -> None:
    response = nightly_lambda.read_nightly_stats_from_s3(BUCKET_NAME, object_key)
    assert response == expected_response


def test_delete_existing_rows_for_date(mock_bigquery_client) -> None:
    date, _type, _ext = OBJECT_KEY_STATS.split('.')

    nightly_lambda.delete_existing_rows_for_date(mock_bigquery_client, BQ_TABLE_ID, OBJECT_KEY_STATS)

    mock_bigquery_client.query.assert_called_once_with(f"DELETE FROM `{BQ_TABLE_ID}` WHERE date = '{date}'")


def test_add_updated_rows_for_date(mock_bigquery_client) -> None:
    nightly_lambda.add_updated_rows_for_date(mock_bigquery_client, BQ_TABLE_ID, example_nightly_stats_bytes())

    _, kwargs = mock_bigquery_client.load_table_from_file.call_args

    assert kwargs['destination'] == BQ_TABLE_ID
    assert kwargs['file_obj'].getvalue() == example_nightly_stats_bytes()


def test_lambda_handler(
    mock_ssm_client,
    mock_s3_client,
    mock_bigquery_client,
) -> None:
    response = nightly_lambda.lambda_handler(EXAMPLE_S3_EVENT_STATS, 'some context')

    assert mock_bigquery_client.query.called
    assert mock_bigquery_client.load_table_from_file.called
    assert mock_bigquery_client.get_table.called

    assert response == {'statusCode': 200}
