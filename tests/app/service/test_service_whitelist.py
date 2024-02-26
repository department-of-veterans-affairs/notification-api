import json

from flask import url_for
from flask_jwt_extended import create_access_token

from app.dao.service_whitelist_dao import dao_add_and_commit_whitelisted_contacts
from app.dao.services_dao import dao_add_user_to_service
from app.models import MANAGE_SETTINGS, Permission
from tests.app.db import create_user
from tests.app.factories.service_whitelist import a_service_whitelist


def _create_auth_header(service=None, platform_admin: bool = False):
    if platform_admin:
        user = create_user(email='foo@bar.com', platform_admin=True)
    else:
        user = create_user(email='foo@bar.com')
        dao_add_user_to_service(
            service, user, permissions=[Permission(service=service, user=user, permission=MANAGE_SETTINGS)]
        )
    token = create_access_token(user)
    return ('Authorization', f'Bearer {token}')


class TestUpdateServiceWhitelist:

    def test_update_whitelist_returns_json_validation_errors(
        self, client, notify_db_session, sample_service, data, error_type, error_message
    ):
        service_whitelist = a_service_whitelist(sample_service.id)
        dao_add_and_commit_whitelisted_contacts([service_whitelist])

        response = client.put(
            url_for('service_whitelist.update_whitelist', service_id=sample_service.id),
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), _create_auth_header(service=sample_service)],
        )

        assert response.status_code == 400
        assert json.loads(response.get_data(as_text=True)) == {
            'errors': [{'error': error_type, 'message': error_message}],
            'status_code': 400,
        }
