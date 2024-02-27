import json
import pytest
from app.dao.templates_dao import dao_update_template, LETTER_TYPE
from app.models import SERVICE_PERMISSION_TYPES
from datetime import datetime, date
from flask import url_for
from uuid import uuid4
from tests import create_admin_authorization_header
from tests.app.db import create_letter_contact


def test_template_history_version(notify_api, sample_user, sample_template):
    template = sample_template()
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            endpoint = url_for(
                'template.get_template_version', service_id=template.service.id, template_id=template.id, version=1
            )
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['id'] == str(template.id)
            assert json_resp['data']['content'] == template.content
            assert json_resp['data']['version'] == 1
            assert json_resp['data']['created_by']['name'] == sample_user().name
            assert datetime.strptime(json_resp['data']['created_at'], '%Y-%m-%d %H:%M:%S.%f').date() == date.today()


def test_previous_template_history_version(notify_api, sample_template):
    template = sample_template()
    old_content = template.content
    template.content = 'New content'
    dao_update_template(template)
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            endpoint = url_for(
                'template.get_template_version', service_id=template.service.id, template_id=template.id, version=1
            )
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['id'] == str(template.id)
            assert json_resp['data']['version'] == 1
            assert json_resp['data']['content'] == old_content


def test_404_missing_template_version(notify_api, sample_template):
    template = sample_template()
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            endpoint = url_for(
                'template.get_template_version', service_id=template.service.id, template_id=template.id, version=2
            )
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            resp = client.get(endpoint, headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404


def test_update_template_reply_to_updates_history(client, sample_template, sample_service):
    service = sample_service(
        service_name=f'sample service full permissions {uuid4()}',
        service_permissions=set(SERVICE_PERMISSION_TYPES),
        check_if_service_exists=True,
    )
    template = sample_template(service=service, template_type=LETTER_TYPE, postage='second')
    auth_header = create_admin_authorization_header()
    letter_contact = create_letter_contact(template.service, 'Edinburgh, ED1 1AA')

    template.reply_to = letter_contact.id
    dao_update_template(template)

    resp = client.get(
        '/service/{}/template/{}/version/2'.format(template.service_id, template.id), headers=[auth_header]
    )
    assert resp.status_code == 200

    hist_json_resp = json.loads(resp.get_data(as_text=True))
    assert 'service_letter_contact_id' not in hist_json_resp['data']
    assert hist_json_resp['data']['reply_to'] == str(letter_contact.id)
    assert hist_json_resp['data']['reply_to_text'] == letter_contact.contact_block
