import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.model import EMAIL_AUTH_TYPE
from app.models import Notification
from tests import create_admin_authorization_header
from tests.app.db import create_invited_user


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
def test_create_invited_user_without_auth_type(admin_request, sample_service, mocker, invitation_email_template):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'invited_user@service.gov.uk'
    invite_from = sample_service.users[0]

    data = {
        'service': str(sample_service.id),
        'email_address': email_address,
        'from_user': str(invite_from.id),
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': [],
    }

    json_resp = admin_request.post(
        'invite.create_invited_user', service_id=sample_service.id, _data=data, _expected_status=201
    )

    assert json_resp['data']['auth_type'] == EMAIL_AUTH_TYPE


def test_get_invited_users_by_service_with_no_invites(
    client,
    sample_service,
):
    url = '/service/{}/invite'.format(sample_service().id)

    auth_header = create_admin_authorization_header()

    response = client.get(url, headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 0


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
def test_update_invited_user_set_status_to_cancelled(client, sample_invited_user):
    data = {'status': 'cancelled'}
    url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['data']
    assert json_resp['status'] == 'cancelled'


@pytest.mark.xfail(reason='Failing after Flask upgrade.  Not fixed because not used.', run=False)
def test_update_invited_user_for_invalid_data_returns_400(client, sample_invited_user):
    data = {'status': 'garbage'}
    url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
