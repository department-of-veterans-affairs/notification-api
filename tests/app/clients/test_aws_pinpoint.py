import pytest
import botocore

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
            origination_number='+10000000000',
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


def test_send_sms_with_service_sender_number(aws_pinpoint_client, boto_mock, mocker):
    test_id = aws_pinpoint_client.aws_pinpoint_app_id
    test_recipient_number = "+100000000"
    test_content = "test content"
    test_reference = 'test notification id'
    test_message_id = 'message-id'
    test_sender = "+12222222222"

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

    aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference, sender=test_sender)

    message_request_payload = {
        "Addresses": {
            test_recipient_number: {
                "ChannelType": "SMS"
            }
        },
        "MessageConfiguration": {
            "SMSMessage": {
                "Body": test_content,
                "MessageType": "TRANSACTIONAL",
                "OriginationNumber": test_sender
            }
        }
    }

    assert boto_mock.send_messages.assert_called_with(ApplicationId=test_id, MessageRequest=message_request_payload)


def test_send_sms_throws_aws_pinpoint_exception(aws_pinpoint_client, boto_mock):
    test_recipient_number = "+1000"
    test_content = "test content"
    test_reference = 'test notification id'

    error_response = {
        'Error': {
            "Code": 400,
            'Message': {
                'RequestID': 'id',
                'Message': "BadRequestException",
            }
        }
    }

    boto_mock.send_messages.side_effect = botocore.exceptions.ClientError(error_response, 'exception')

    with pytest.raises(AwsPinpointException) as exception:
        aws_pinpoint_client.send_sms(test_recipient_number, test_content, test_reference)

    assert f"BadRequestException" in str(exception.value)
    aws_pinpoint_client.statsd_client.incr.assert_called_with("clients.sms.error")
