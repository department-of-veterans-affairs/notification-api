import pytest

from app.integrations.comp_and_pen.scheduled_message_helpers import CompPenMsgHelper


@pytest.fixture
def msg_helper(mocker, dynamodb_mock) -> CompPenMsgHelper:
    # Mocks necessary for dynamodb
    mocker.patch('boto3.resource')
    helper = CompPenMsgHelper('test')
    mocker.patch.object(helper, 'dynamodb_table', dynamodb_mock)
    return helper
