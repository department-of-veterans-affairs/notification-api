"""
from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
    process_body_from_alb_invocation,
    push_to_retry_sqs,
    vetext_incoming_forwarder_lambda_handler,
)
"""

import pytest
import json
import base64
import requests



# foo = {'requestContext': {'elb': {'targetGroupArn': 'arn:aws-us-gov:elasticloadbalancing:us-gov-west-1:171875617347:targetgroup/staging-vetext-incoming-tg/954436fa4944a16e'}}, 'httpMethod': 'POST', 'path': '/twoway/vettext', 'queryStringParameters': {}, 'headers': {'accept': '*/*', 'connection': 'close', 'content-length': '591', 'content-type': 'application/x-www-form-urlencoded', 'host': 'staging-api.va.gov', 'i-twilio-idempotency-token': '31b12870-a9e7-4003-b54c-3fa6ea86e855', 'user-agent': 'TwilioProxy/1.1', 'x-amzn-trace-id': 'Self=1-6601a10d-12e6bc7e33e487063346cd27;Root=1-6601a10d-4d777b8c255389f577097616', 'x-forwarded-for': '3.80.20.121, 10.238.28.71, 3.80.20.121, 10.247.34.67', 'x-forwarded-host': 'staging-api.va.gov:443', 'x-forwarded-port': '443', 'x-forwarded-proto': 'https', 'x-forwarded-scheme': 'https', 'x-home-region': 'us1', 'x-real-ip': '3.80.20.121', 'x-twilio-signature': 'oTLU4P2B2q5Xr9xD10bpMJpJJzo=', 'x-use-static-proxy': 'true'}, 'body': 'VG9Db3VudHJ5PVVTJlRvU3RhdGU9VFgmU21zTWVzc2FnZVNpZD1TTTI3OGQwMDc2MTUxMWRiNGY5ODA4YzIyMTRhZGRlMDg0Jk51bU1lZGlhPTAmVG9DaXR5PSZGcm9tWmlwPTMyNDQ0JlNtc1NpZD1TTTI3OGQwMDc2MTUxMWRiNGY5ODA4YzIyMTRhZGRlMDg0JkZyb21TdGF0ZT1GTCZTbXNTdGF0dXM9cmVjZWl2ZWQmRnJvbUNpdHk9UEFOQU1BK0NJVFkmQm9keT1Ib3crYWJvdXQrYW5vdGhlcit0ZXN0Ky0rS3lsZSZGcm9tQ291bnRyeT1VUyZUbz0lMkIxMjU0MjcxMzUzMSZNZXNzYWdpbmdTZXJ2aWNlU2lkPU1HYTkyNmM5YjU4NTczMDdkOGIxYzJjYWJlZGMyM2IwYzkmVG9aaXA9JkFkZE9ucz0lN0IlMjJzdGF0dXMlMjIlM0ElMjJzdWNjZXNzZnVsJTIyJTJDJTIybWVzc2FnZSUyMiUzQW51bGwlMkMlMjJjb2RlJTIyJTNBbnVsbCUyQyUyMnJlc3VsdHMlMjIlM0ElN0IlN0QlN0QmTnVtU2VnbWVudHM9MSZNZXNzYWdlU2lkPVNNMjc4ZDAwNzYxNTExZGI0Zjk4MDhjMjIxNGFkZGUwODQmQWNjb3VudFNpZD1BQzU1MWZjNjA4NmY5M2E4MzQ5MjQ2NmZjNjA0YzY4YWY0JkZyb209JTJCMTg1MDYyODMzNTImQXBpVmVyc2lvbj0yMDEwLTA0LTAx', 'isBase64Encoded': True}
# bar = {'requestContext': {'elb': {'targetGroupArn': 'arn:aws-us-gov:elasticloadbalancing:us-gov-west-1:171875617347:targetgroup/staging-vetext-incoming-tg/954436fa4944a16e'}}, 'httpMethod': 'POST', 'path': '/twoway/vetext2', 'queryStringParameters': {}, 'headers': {'accept': '*/*', 'connection': 'close', 'content-length': '567', 'content-type': 'application/x-www-form-urlencoded', 'host': 'staging-api.va.gov', 'i-twilio-idempotency-token': '2228ddd2-f727-478e-a314-7a2429657153', 'user-agent': 'TwilioProxy/1.1', 'x-amzn-trace-id': 'Self=1-6601a059-434164cf701e5bc44755fd3b;Root=1-6601a059-594d7b8172693bb0331fe59d', 'x-forwarded-for': '3.80.20.64, 10.238.28.71, 3.80.20.64, 10.247.35.101', 'x-forwarded-host': 'staging-api.va.gov:443', 'x-forwarded-port': '443', 'x-forwarded-proto': 'https', 'x-forwarded-scheme': 'https', 'x-home-region': 'us1', 'x-real-ip': '3.80.20.64', 'x-twilio-signature': '81MF5dhNjYekgMLnDNrMuhOBMaE=', 'x-use-static-proxy': 'true'}, 'body': 'VG9Db3VudHJ5PVVTJlRvU3RhdGU9VFgmU21zTWVzc2FnZVNpZD1TTWIxYTE2ZTFjZGIxZmIzN2U0ZDk5NzUzYTUxZDdkNzY4Jk51bU1lZGlhPTAmVG9DaXR5PSZGcm9tWmlwPTMyNDQ0JlNtc1NpZD1TTWIxYTE2ZTFjZGIxZmIzN2U0ZDk5NzUzYTUxZDdkNzY4JkZyb21TdGF0ZT1GTCZTbXNTdGF0dXM9cmVjZWl2ZWQmRnJvbUNpdHk9UEFOQU1BK0NJVFkmQm9keT1UZXN0MiZGcm9tQ291bnRyeT1VUyZUbz0lMkIxNDY5NjA2MzM5MCZNZXNzYWdpbmdTZXJ2aWNlU2lkPU1HMzA2MzU5YzY3ZjgzOThlZDAwODIzZDliM2JhOGJiMGYmVG9aaXA9JkFkZE9ucz0lN0IlMjJzdGF0dXMlMjIlM0ElMjJzdWNjZXNzZnVsJTIyJTJDJTIybWVzc2FnZSUyMiUzQW51bGwlMkMlMjJjb2RlJTIyJTNBbnVsbCUyQyUyMnJlc3VsdHMlMjIlM0ElN0IlN0QlN0QmTnVtU2VnbWVudHM9MSZNZXNzYWdlU2lkPVNNYjFhMTZlMWNkYjFmYjM3ZTRkOTk3NTNhNTFkN2Q3NjgmQWNjb3VudFNpZD1BQzU1MWZjNjA4NmY5M2E4MzQ5MjQ2NmZjNjA0YzY4YWY0JkZyb209JTJCMTg1MDYyODMzNTImQXBpVmVyc2lvbj0yMDEwLTA0LTAx', 'isBase64Encoded': True}


albInvokeWithAddOn = {
    'requestContext': {
        'elb': {
            'targetGroupArn': 'arn:aws-us-gov:elasticloadbalancing:us-gov-west-1:TEST:targetgroup/prod-vetext-incoming-tg/235ef4ac03a4706b'
        }
    },
    'httpMethod': 'POST',
    'path': '/twoway/vettext',
    'queryStringParameters': {},
    'headers': {
        'accept': '*/*',
        'connection': 'close',
        'content-length': '574',
        'content-type': 'application/x-www-form-urlencoded',
        'host': 'api.va.gov',
        'i-twilio-idempotency-token': 'edf7e44c-3116-4261-8ef6-e762ca6a4fce',
        'user-agent': 'TwilioProxy/1.1',
        'x-amzn-trace-id': 'Self=1-62d5ee4d-2cb5b7303f8e994a1f5cb6e1;Root=1-62d5ee4d-24b4119d5098534860221d75',
        'x-forwarded-for': '3.89.199.39, 10.239.28.71, 3.89.199.39, 10.247.33.103',
        'x-forwarded-host': 'api.va.gov:443',
        'x-forwarded-port': '443',
        'x-forwarded-proto': 'https',
        'x-forwarded-scheme': 'https',
        'x-home-region': 'us1',
        'x-real-ip': '3.89.199.39',
        'x-twilio-signature': 'G3loUGCg54DEz1eJVeMUvkrovsk=',
    },
    'body': 'U21zU2lkPXRoaXNpc3NvbWVzbXNpZCZTbXNTdGF0dXM9c2VudCZNZXNzYWdlU3RhdHVzPXNlbnQmVG89JTJCMTExMTExMTExMTEmTWVzc2FnZVNpZD1zb21lbWVzc2FnZWlkZW50aWZpZXImQWNjb3VudFNpZD10d2lsaW9hY2NvdW50c2lkJkZyb209JTJCMjIyMjIyMjIyMiZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=',
    'isBase64Encoded': True,
}

albInvokedWithoutAddOn = {
    'requestContext': {'elb': {'targetGroupArn': ''}},
    'httpMethod': 'POST',
    'path': '/twoway/vettext',
    'queryStringParameters': {},
    'headers': {
        'accept': '*/*',
        'connection': 'close',
        'content-length': '552',
        'content-type': 'application/x-www-form-urlencoded',
        'host': 'api.va.gov',
        'i-twilio-idempotency-token': '09f6d617-b893-4864-8f42-24a36ec48691',
        'user-agent': 'TwilioProxy/1.1',
        'x-amzn-trace-id': '',
        'x-forwarded-for': '',
        'x-forwarded-host': 'api.va.gov:443',
        'x-forwarded-port': '443',
        'x-forwarded-proto': 'https',
        'x-forwarded-scheme': 'https',
        'x-home-region': 'us1',
        'x-real-ip': '',
        'x-twilio-signature': 'G3loUGCg54DEz1eJVeMUvkrovsk=',
        'x-use-static-proxy': 'true',
    },
    'body': 'U21zU2lkPXRoaXNpc3NvbWVzbXNpZCZTbXNTdGF0dXM9c2VudCZNZXNzYWdlU3RhdHVzPXNlbnQmVG89JTJCMTExMTExMTExMTEmTWVzc2FnZVNpZD1zb21lbWVzc2FnZWlkZW50aWZpZXImQWNjb3VudFNpZD10d2lsaW9hY2NvdW50c2lkJkZyb209JTJCMjIyMjIyMjIyMiZBcGlWZXJzaW9uPTIwMTAtMDQtMDE=',
}

sqsInvokedWithAddOn = {
    'Records': [
        {
            'messageId': '143555b0-a74b-4793-8421-15cfeeaa487d',
            'receiptHandle': 'AQEBfoQLBPET91yTrBH2AEToheRAt2X8vrQddfzr8CG4haD0LT+leMdW7uiDW9AEvr6YMbTVBgYNSBUegTU/g3KQ6deY1NqQxba+2j0KnHiiSrnzuotJAcSItGGjKh2kr4mxU/zg+WMmD1949uCS+og+x9Ayxy0762PtFiQ//vT1fiMVvCXtArDQHnj6p0ywENGq99TE/71UYXPn2WuuQcGgGvEi4kOYzz0u4/iQxH8kWz5u7Qroumob/4EVe7uAu6FCzSYylY+6yCHnDMCtqVKKndr1RP/hUiGkp/Cy8nZew2yh7lJvIIvi9hZjMi8/HQs8725HV1/83hOukYq8IrWIT0tDjDI49Xn/cOjzMGpbRmchr5tk4JOBM8Btg0JkkuM8Js7an5PiuvRS0sqeX1INTZQDCl7nOqNbPjqx0FKgDzg=',
            'body': '{"ToCountry": "US", "SmsMessageSid": "TESTSMSMESSAGESID", "NumMedia": "0", "FromZip": "74344", "SmsSid": "SM031265e1d5c5e56c6243509a1eafc7e8", "FromState": "OK", "SmsStatus": "received", "FromCity": "GROVE", "Body": "Y1", "FromCountry": "US", "To": "53079", "MessagingServiceSid": "testMessageServiceSid", "NumSegments": "1", "ReferralNumMedia": "0", "MessageSid": "TESTMESSAGEID", "AccountSid": "TESTACCOUNTSID", "From": "+1111111111", "ApiVersion": "2010-04-01"}',
            'attributes': {
                'ApproximateReceiveCount': '1',
                'SentTimestamp': '1658165878744',
                'SenderId': 'AROASQBEVZJB7JNKLLQIY:project-prod-vetext-incoming-forwarder-lambda',
                'ApproximateFirstReceiveTimestamp': '1658245723375',
            },
            'messageAttributes': {
                'source': {
                    'stringValue': 'twilio',
                    'stringListValues': [],
                    'binaryListValues': [],
                    'dataType': 'String',
                }
            },
            'md5OfMessageAttributes': '54818a2ef8e5363fbdb8d318121ef7c4',
            'md5OfBody': '63d3b9430c4741f41a20554ed655db1f',
            'eventSource': 'aws:sqs',
            'eventSourceARN': 'arn:aws-us-gov:sqs:us-gov-west-1:TEST:prod-vetext-failed-request-queue',
            'awsRegion': 'us-gov-west-1',
        }
    ]
}

VETEXT_URI_PATH = '/some/path'
VETEXT_DOMAIN = 'some.domain'


# This method will be used by the mock to replace requests.post
class MockResponse:
    def __init__(self, json_data, status_code, content=None):
        self.json_data = json_data
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        return {}

    def json(self):
        return self.json_data


def mocked_requests_post_success(*args, **kwargs):
    return MockResponse({}, 200, '<?xml version="1.0" encoding="UTF-8"?><Response></Response>')


def mocked_requests_post_404(*args, **kwargs):
    return MockResponse({}, 404)


def mocked_requests_httperror_exception():
    return requests.exceptions.HTTPError()


@pytest.fixture
def missing_domain_env_param(monkeypatch):
    monkeypatch.setenv('vetext_api_endpoint_path', VETEXT_URI_PATH)
    monkeypatch.setenv('vetext_api_auth_ssm_path', 'ssm')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN_SSM_NAME', 'unit_test')


@pytest.fixture
def missing_api_endpoint_path_env_param(monkeypatch):
    monkeypatch.setenv('vetext_api_endpoint_domain', VETEXT_DOMAIN)
    monkeypatch.setenv('vetext_api_auth_ssm_path', 'ssm')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN_SSM_NAME', 'unit_test')


@pytest.fixture
def missing_ssm_path_env_param(monkeypatch):
    monkeypatch.setenv('vetext_api_endpoint_domain', VETEXT_DOMAIN)
    monkeypatch.setenv('vetext_api_endpoint_path', VETEXT_URI_PATH)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN_SSM_NAME', 'unit_test')


@pytest.fixture
def all_path_env_param_set(monkeypatch):
    monkeypatch.setenv('vetext_api_endpoint_domain', VETEXT_DOMAIN)
    monkeypatch.setenv('vetext_api_endpoint_path', VETEXT_URI_PATH)

    monkeypatch.setenv('VETEXT2_API_ENDPOINT_DOMAIN', f'{VETEXT_DOMAIN}-two')
    monkeypatch.setenv('VETEXT2_API_ENDPOINT_PATH', f'{VETEXT_URI_PATH}/two')

    monkeypatch.setenv('vetext_api_auth_ssm_path', 'ssm')
    monkeypatch.setenv('VETEXT2_BASIC_AUTH_SSM_PATH', 'ssm_two')

    monkeypatch.setenv('vetext_request_drop_sqs_url', 'someurl')
    monkeypatch.setenv('vetext_request_dead_letter_sqs_url', 'someurl')

    monkeypatch.setenv('TWILIO_AUTH_TOKEN_SSM_NAME', 'unit_test')


LAMBDA_MODULE = 'lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda'


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn)])
def test_verify_parsing_of_twilio_message(monkeypatch, all_path_env_param_set, event):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        process_body_from_alb_invocation,
    )
    response = process_body_from_alb_invocation(event)

    assert response, 'The dictionary should not be empty'
    assert 'AddOns' not in response


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_request_makes_vetext_call(mocker, monkeypatch, all_path_env_param_set, event):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )
    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    mock_requests = mocker.patch(f'{LAMBDA_MODULE}.requests.post', return_value=mocked_requests_post_success())
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert mock_requests.call_count == 1
    assert mock_requests.call_args[0][0] == f'https://{VETEXT_DOMAIN}{VETEXT_URI_PATH}'

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_not_called()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn)])
def test_request_makes_vetext2_call(mocker, monkeypatch, all_path_env_param_set, event):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    mock_requests = mocker.patch(f'{LAMBDA_MODULE}.requests.post', return_value=mocked_requests_post_success())

    event['path'] = '/twoway/vetext2'
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert mock_requests.call_count == 1
    assert mock_requests.call_args[0][0] == 'https://some.domain-two/some/path/two'

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_not_called()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_vetext_call_goes_to_retry_sqs(mocker, event, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    mocker.patch(f'{LAMBDA_MODULE}.requests.post', return_value=mocked_requests_post_404())

    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_vetext_call_throws_http_exception_goes_to_retry_sqs(mocker, event, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    mocker.patch(
        f'{LAMBDA_MODULE}.requests.post',
        return_value=mocked_requests_httperror_exception(),
    )

    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_vetext_call_throws_general_exception_goes_to_retry_sqs(
    mocker, event, monkeypatch, all_path_env_param_set
):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    mocker.patch(f'{LAMBDA_MODULE}.requests.post', side_effect=Exception)
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


@pytest.mark.parametrize('event', [(sqsInvokedWithAddOn)])
def test_failed_sqs_invocation_call_throws_general_exception_goes_to_dead_letter_sqs(
    mocker, event, monkeypatch, all_path_env_param_set
):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.process_body_from_sqs_invocation', side_effect=Exception)
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 500
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_not_called()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn)])
def test_failed_alb_invocation_call_throws_general_exception_goes_to_dead_letter_sqs(
    mocker, event, monkeypatch, all_path_env_param_set
):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.process_body_from_alb_invocation', side_effect=Exception)
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 500
    assert response['body'] == '<Response />'
    sqs_mock.assert_not_called()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_eventbody_moved_to_retry_sqs_when_ssm_paramter_returns_empty_string(
    mocker, event, monkeypatch, all_path_env_param_set
):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='')
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


# GetEnv checks should go on queue


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_getenv_vetext_api_endpoint_domain_property(mocker, missing_domain_env_param, event, monkeypatch):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_getenv_vetext_api_endpoint_path(mocker, missing_api_endpoint_path_env_param, event, monkeypatch):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


@pytest.mark.parametrize('event', [(albInvokedWithoutAddOn), (albInvokeWithAddOn), (sqsInvokedWithAddOn)])
def test_failed_getenv_vetext_api_auth_ssm_path(mocker, missing_ssm_path_env_param, event, monkeypatch):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_retry_sqs')
    mocker.patch(f'{LAMBDA_MODULE}.read_from_ssm', return_value='ssm')
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_mock.assert_called_once()


def test_unexpected_event_received(mocker, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_dead_letter_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_dead_letter_sqs')
    event = {}
    response = vetext_incoming_forwarder_lambda_handler(event, False)

    assert response['statusCode'] == 500
    assert response['body'] == '<Response />'
    sqs_dead_letter_mock.assert_called_once()


def test_sqs_dead_letter_queue_called(mocker, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    sqs_dead_letter_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_dead_letter_sqs')

    mocker.patch('json.loads', side_effect=json.decoder.JSONDecodeError)
    response = vetext_incoming_forwarder_lambda_handler(sqsInvokedWithAddOn, False)

    assert response['statusCode'] == 200
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_dead_letter_mock.assert_called_once()


def test_loading_message_from_alb_fails(mocker, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )
    sqs_dead_letter_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_dead_letter_sqs')

    mocker.patch('base64.b64decode', side_effect=base64.binascii.Error)
    response = vetext_incoming_forwarder_lambda_handler(albInvokedWithoutAddOn, False)

    assert response['statusCode'] == 403
    assert response['body'] == '<Response />'
    assert response['headers'] is not None
    assert response['headers']['Content-Type'] == 'text/xml'

    sqs_dead_letter_mock.assert_not_called()


def test_loading_message_from_sqs_called_once(mocker, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import push_to_retry_sqs

    sqs_dead_letter_mock = mocker.patch(f'{LAMBDA_MODULE}.push_to_dead_letter_sqs')

    mocker.patch('json.dumps', side_effect=Exception)
    push_to_retry_sqs(albInvokedWithoutAddOn)

    sqs_dead_letter_mock.assert_called_once()


def test_twilio_validate_failure(mocker, monkeypatch, all_path_env_param_set):
    from lambda_functions.vetext_incoming_forwarder_lambda.vetext_incoming_forwarder_lambda import (
        vetext_incoming_forwarder_lambda_handler,
    )

    broken_headers = albInvokedWithoutAddOn
    broken_headers['headers']['x-twilio-signature'] = 'spoofed'
    response = vetext_incoming_forwarder_lambda_handler(broken_headers, True)
    assert response['statusCode'] == 403

    missing_header = broken_headers
    del missing_header['headers']['x-twilio-signature']
    response = vetext_incoming_forwarder_lambda_handler(missing_header, True)
    assert response['statusCode'] == 403
