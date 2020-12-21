import pytest
import requests_mock
from requests_mock import ANY

from app.clients.sms.aws_pinpoint import AwsPinpointClient, AwsPinpointException


@pytest.fixture(scope='function')
def aws_pinpoint_client(notify_api, mocker):
    with notify_api.app_context():
        aws_pinpoint_client = AwsPinpointClient()
        statsd_client = mocker.Mock()
        logger = mocker.Mock()
        aws_pinpoint_client.init_app(
            aws_pinpoint_app_id='some-app-id',
            aws_region='some-aws-region',
            logger=logger,
            origination_number='some_number',
            statsd_client=statsd_client
        )
        return aws_pinpoint_client


@pytest.fixture(scope='function')
def boto_mock(aws_pinpoint_client, mocker):
    boto_mock = mocker.patch.object(aws_pinpoint_client, '_client', create=True)
    return boto_mock


def test_send_sms_successful_returns_aws_pinpoint_response_messageid(aws_pinpoint_client, boto_mock):
    test_id = 'some_id'
    test_recipient_number = "+100000000"
    test_content = "test content"
    test_reference = 'test notification id'
    test_message_id = 'message-id'

    boto_mock.send_messages.return_value = {
        'MessageResponse': {
            'ApplicationId': test_id,
            'RequestId': 'request-id',
            'Result': {
                test_recipient_number: {
                    'DeliveryStatus': 'SUCCESSFUL',
                    'MessageId': test_message_id,
                    'StatusCode': 200,
                    'StatusMessage': f"MessageId: {test_message_id}",
                }
            }
        }
    }

    response = aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference)

    assert response == test_message_id


def test_send_sms_throws_bad_request_exception(aws_pinpoint_client, rmock):
    test_recipient_number = "+1000"
    test_content = "test content"
    test_reference = 'test notification id'
    exception_response = {
        "RequestID": "id",
        "Message": "Bad Syntax Request"
    }
    rmock.post(
        ANY,
        json=exception_response,
        status_code=400
    )
    with pytest.raises(AwsPinpointException):
        aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference)


@pytest.mark.skip
def test_draft(aws_pinpoint_client, rmock):
    test_id = 'some_id'
    test_recipient_number = "+100000000"
    test_content = "test content"
    test_reference = 'test notification id'
    test_message_id = 'message-id'

    response_from_post_message_request = {
        'MessageResponse': {
            'ApplicationId': test_id,
            'RequestId': 'request-id',
            'Result': {
                test_recipient_number: {
                    'DeliveryStatus': 'SUCCESSFUL',
                    'MessageId': test_message_id,
                    'StatusCode': 200,
                    'StatusMessage': f"MessageId: {test_message_id}",
                }
            }
        }
    }
    rmock.request(
        'POST',
        requests_mock.ANY,
        json=response_from_post_message_request,
        status_code=200
    )

    # with requests_mock.mock() as mock123:
    #     mock123.request('POST', ANY, json=response_from_post_message_request, status_code=200)
    #
    # response = aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference)
    # assert response == 'boo'

    response = aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference)

    assert response == test_message_id
