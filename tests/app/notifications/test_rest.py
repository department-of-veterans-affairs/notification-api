"""
This module tests GET requests to /notifications endpoints.
"""

import pytest
import uuid
from app.dao.notifications_dao import dao_update_notification
from app.dao.templates_dao import dao_update_template
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    SMS_TYPE,
)
from flask import current_app
from freezegun import freeze_time
from tests import create_authorization_header


def test_get_notification_empty_result(
    client,
    sample_api_key,
):
    auth_header = create_authorization_header(sample_api_key())

    response = client.get(path='/notifications/{}'.format(uuid.uuid4()), headers=[auth_header])

    assert response.status_code == 404
    response_json = response.get_json()
    assert response_json['result'] == 'error'
    assert response_json['message'] == 'No result found'


def test_should_reject_invalid_page_param(
    client,
    sample_api_key,
):
    auth_header = create_authorization_header(sample_api_key())

    response = client.get('/notifications?page=invalid', headers=[auth_header])

    assert response.status_code == 400
    response_json = response.get_json()
    assert response_json['result'] == 'error'
    assert 'Not a valid integer.' in response_json['message']['page']


def test_get_all_notifications_returns_empty_list(
    client,
    sample_api_key,
):
    auth_header = create_authorization_header(sample_api_key())

    response = client.get('/notifications', headers=[auth_header])

    assert response.status_code == 200
    response_json = response.get_json()
    assert len(response_json['notifications']) == 0


def test_filter_by_multiple_template_types(
    client,
    sample_api_key,
    sample_notification,
    sample_template,
):
    email_template = sample_template(template_type=EMAIL_TYPE)
    sample_notification(template=sample_template(service=email_template.service))
    sample_notification(template=email_template)

    auth_header = create_authorization_header(sample_api_key(service=email_template.service))

    response = client.get('/notifications?template_type=sms&template_type=email', headers=[auth_header])

    assert response.status_code == 200
    response_json = response.get_json()['notifications']
    assert len(response_json) == 2
    assert {SMS_TYPE, EMAIL_TYPE} == set(x['template']['template_type'] for x in response_json)
