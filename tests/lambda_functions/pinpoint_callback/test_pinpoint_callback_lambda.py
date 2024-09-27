import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws


@mock_aws
def create_sqs_queue():
    # when this is a fixture, it doesn't work for some reason ¯\_(ツ)_/¯
    sqs = boto3.resource('sqs')
    sqs.create_queue(QueueName='vanotify-delivery-status-result-tasks')


@mock_aws
def test_pinpoint_callback_lambda_raises_client_error():
    with pytest.raises(ClientError):
        from lambda_functions.pinpoint_callback.pinpoint_callback_lambda import lambda_handler

        event = {'Records': [{'kinesis': {'data': 'test-data'}}]}
        context = {}
        lambda_handler(event, context)


@mock_aws
def test_pinpoint_callback_lambda_handler_success():
    # there has to be a better way to do this, right?
    create_sqs_queue()
    from lambda_functions.pinpoint_callback.pinpoint_callback_lambda import lambda_handler

    # test data
    event = {'Records': [{'kinesis': {'data': 'test-data'}}]}
    context = {}
    response = lambda_handler(event, context)

    assert response == {'statusCode': 200}
