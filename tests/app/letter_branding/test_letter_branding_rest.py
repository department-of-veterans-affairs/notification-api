import uuid

from tests import create_authorization_header


def test_get_letter_branding_by_id_returns_404_if_does_not_exist(client, notify_db_session):
    response = client.get('/letter-branding/{}'.format(uuid.uuid4()), headers=[create_authorization_header()])
    assert response.status_code == 404
