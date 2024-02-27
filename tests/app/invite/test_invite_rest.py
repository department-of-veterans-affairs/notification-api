import json

from tests import create_admin_authorization_header


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
