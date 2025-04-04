import json
import uuid

import pytest
from jsonschema import ValidationError

from app.constants import DELIVERY_STATUS_CALLBACK_TYPE, WEBHOOK_CHANNEL_TYPE
from app.schema_validation import validate
from app.service.service_callback_api_schema import (
    create_service_callback_api_request_schema,
    update_service_callback_api_request_schema,
)
from app.service.service_senders_schema import update_service_sms_sender_request


def test_create_service_callback_api_schema_validate_succeeds(client):
    under_test = {
        'url': 'https://some_url.for_service',
        'bearer_token': 'something_ten_chars',
        'notification_statuses': ['failed'],
        'callback_channel': WEBHOOK_CHANNEL_TYPE,
        'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
    }

    assert validate(under_test, create_service_callback_api_request_schema) == under_test


@pytest.mark.parametrize('key, value', [(None, None)])
def test_create_service_callback_api_schema_validate_fails_when_missing_properties(client, key, value):
    under_test = {key: value}

    with pytest.raises(ValidationError) as e:
        validate(under_test, create_service_callback_api_request_schema)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) >= 1
    for message in errors:
        assert message['error'] == 'ValidationError'
        assert 'is a required property' in message['message']


@pytest.mark.parametrize(
    'key, wrong_key, value',
    [
        ('url', 'urls', 'https://some_url.for_service'),
    ],
)
def test_create_service_callback_api_schema_validate_fails_with_misspelled_keys(client, key, wrong_key, value):
    under_test = {
        'url': 'https://some_url.for_service',
        'bearer_token': 'something_ten_chars',
        'notification_statuses': ['failed'],
        'callback_channel': WEBHOOK_CHANNEL_TYPE,
        'callback_type': DELIVERY_STATUS_CALLBACK_TYPE,
    }
    del under_test[key]
    under_test[wrong_key] = value

    with pytest.raises(ValidationError) as e:
        validate(under_test, create_service_callback_api_request_schema)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert errors[0]['error'] == 'ValidationError'
    assert errors[0]['message'] == f'{key} is a required property'


def test_update_service_callback_api_schema_validate_succeeds(client):
    under_test = {
        'url': 'https://some_url.for_service',
        'bearer_token': 'something_ten_chars',
    }

    assert validate(under_test, update_service_callback_api_request_schema) == under_test


def test_update_service_callback_api_schema_validate_fails_with_invalid_keys(client):
    under_test = {
        'bearers_token': 'something_ten_chars',
    }

    with pytest.raises(ValidationError) as e:
        validate(under_test, update_service_callback_api_request_schema)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert errors[0]['error'] == 'ValidationError'
    assert 'bearers_token' in errors[0]['message']


def test_update_service_sms_sender_request_schema_validates(client):
    under_test = {
        'sms_sender': 'sender',
        'sms_sender_specifics': {
            'some': 'data',
            'other_data': 15.3,
        },
        'is_default': True,
        'rate_limit': 3000,
        'rate_limit_interval': 1,
        'inbound_number_id': str(uuid.uuid4()),
    }

    assert validate(under_test, update_service_sms_sender_request) == under_test
