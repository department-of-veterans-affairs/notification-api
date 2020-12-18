import pytest
from flask import Flask

from app.clients.sms.aws_pinpoint import AwsPinpointClient
from app.config import configs

app = Flask('test')
app.config.from_object(configs['test'])


@pytest.fixture(scope='function')
def aws_pinpoint_client(mocker):
    aws_pinpoint_client = AwsPinpointClient()
    statsd_client = mocker.Mock()
    logger = mocker.Mock()
    aws_pinpoint_client.init_app('some-aws-region', 'some_number', statsd_client, logger)
    return aws_pinpoint_client


@pytest.fixture(scope='function')
def boto_mock(aws_pinpoint_client, mocker):
    boto_mock = mocker.patch.object(aws_pinpoint_client, '_client', create=True)
    return boto_mock


def test_get_application_id_returns_id(aws_pinpoint_client, boto_mock):
    test_id = 'some_id'

    boto_mock.get_apps.return_value = {
        'ApplicationsResponse': {
            'Item': [
                {
                    'Arn': 'some value',
                    'Id': test_id,
                    'Name': 'project-test-notification-api',
                    'tags': {}
                }
            ]
        }
    }

    with app.app_context():
        app_id = aws_pinpoint_client.get_application_id()

        assert app_id == test_id
