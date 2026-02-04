import json
import os

import pytest
from celery.exceptions import CeleryError
from flask import url_for
from kombu.exceptions import OperationalError

from app.constants import PUSH_TYPE
from app.mobile_app.mobile_app_types import DEFAULT_MOBILE_APP_TYPE
from tests import create_authorization_header


def test_mobile_app_push_notification_delivered(
    client,
    rmock,
    mocker,
    sample_api_key,
    sample_service,
):
    service = sample_service(service_permissions=[PUSH_TYPE])
    api_key = sample_api_key(service=service)
    rmock.register_uri(
        'POST', f'{client.application.config["VETEXT_URL"]}/mobile/push/send', json={'result': 'success'}
    )

    mocker.patch('app.v2.notifications.rest_push.deliver_push')
    push_request_body = {
        'mobile_app': DEFAULT_MOBILE_APP_TYPE,
        'template_id': 'some-template-id',
        'recipient_identifier': {'id_type': 'ICN', 'id_value': 'some-icn'},
        'personalisation': {'%FOO%': 'bar'},
    }

    mocker.patch.dict(os.environ, {f'{DEFAULT_MOBILE_APP_TYPE}_SID': '1234'})

    response = client.post(
        url_for('v2_notifications.send_push_notification', service_id=service.id),
        data=json.dumps(push_request_body),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(api_key),
        ],
    )

    assert response.json.get('result') == 'success'
    assert response.status_code == 201


@pytest.mark.parametrize('app', [None, 'mobile_app'])
def test_mobile_app_push_notification_failed_validation(
    client,
    rmock,
    mocker,
    sample_api_key,
    sample_service,
    app,
):
    service = sample_service(service_permissions=[PUSH_TYPE])
    api_key = sample_api_key(service=service)
    rmock.register_uri(
        'POST', f'{client.application.config["VETEXT_URL"]}/mobile/push/send', json={'result': 'success'}
    )

    push_request_body = {}

    # Test mobile_app there and not there cases
    if app is not None:
        push_request_body['mobile_app'] = DEFAULT_MOBILE_APP_TYPE
        mocker.patch.dict(os.environ, {f'{DEFAULT_MOBILE_APP_TYPE}_SID': '1234'})

    response = client.post(
        url_for('v2_notifications.send_push_notification', service_id=service.id),
        data=json.dumps(push_request_body),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(api_key),
        ],
    )

    assert 'ValidationError' in str(response.json)
    assert response.status_code == 400


@pytest.mark.parametrize('test_exception', [CeleryError, OperationalError])
def test_mobile_app_push_notification_celery_exception(
    client,
    test_exception,
    rmock,
    mocker,
    sample_api_key,
    sample_service,
):
    service = sample_service(service_permissions=[PUSH_TYPE])
    api_key = sample_api_key(service=service)

    mocker.patch('app.v2.notifications.rest_push.deliver_push.apply_async', side_effect=test_exception)
    push_request_body = {
        'mobile_app': DEFAULT_MOBILE_APP_TYPE,
        'template_id': 'some-template-id',
        'recipient_identifier': {'id_type': 'ICN', 'id_value': 'some-icn'},
        'personalisation': {'%FOO%': 'bar'},
    }

    mocker.patch.dict(os.environ, {f'{DEFAULT_MOBILE_APP_TYPE}_SID': '1234'})

    response = client.post(
        url_for('v2_notifications.send_push_notification', service_id=service.id),
        data=json.dumps(push_request_body),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(api_key),
        ],
    )

    assert response.json.get('result') == 'error'
    assert response.status_code == 503
