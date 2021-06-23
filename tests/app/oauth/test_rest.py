import json
import os

import pytest
from authlib.integrations.base_client import OAuthError
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt import ExpiredSignatureError
from requests import Response
from requests.exceptions import HTTPError
from sqlalchemy.orm.exc import NoResultFound

from app.feature_flags import FeatureFlag
from app.models import User
from app.oauth.exceptions import OAuthException, IncorrectGithubIdException
from app.oauth.rest import make_github_get_request
from tests.conftest import set_config_values


def mock_toggle(mocker, feature_flag: FeatureFlag, enabled: str) -> None:
    mocker.patch.dict(os.environ, {feature_flag.value: enabled})


@pytest.fixture
def github_login_toggle_disabled(mocker):
    mock_toggle(mocker, FeatureFlag.GITHUB_LOGIN_ENABLED, 'False')


@pytest.fixture
def github_login_toggle_enabled(mocker):
    mock_toggle(mocker, FeatureFlag.GITHUB_LOGIN_ENABLED, 'True')


@pytest.fixture
def login_with_password_toggle_enabled(mocker):
    mock_toggle(mocker, FeatureFlag.EMAIL_PASSWORD_LOGIN_ENABLED, 'True')


@pytest.fixture
def login_with_password_toggle_disabled(mocker):
    mock_toggle(mocker, FeatureFlag.EMAIL_PASSWORD_LOGIN_ENABLED, 'False')


@pytest.fixture
def identity_provider_authorization_url():
    return "https://github.com/login/oauth/authorize"


@pytest.fixture
def cookie_config():
    return {
        'UI_HOST_NAME': 'https://some-ui-host-name.com',
        'JWT_ACCESS_COOKIE_NAME': 'cookie-name'
    }


@pytest.fixture
def success_github_org_membership(mocker):
    github_org_membership = {
        "url": "https://api.github.com/orgs/department-of-veterans-affairs/memberships/some-user",
        "state": "pending",
        "role": "user",
        "organization_url": "https://api.github.com/orgs/department-of-veterans-affairs",
        "organization": {
            "login": "department-of-veterans-affairs",
            "id": 1,
            "node_id": "blahblahblah",
            "url": "https://api.github.com/orgs/department-of-veterans-affairs",
            "repos_url": "https://api.github.com/orgs/department-of-veterans-affairs/repos",
            "events_url": "https://api.github.com/orgs/department-of-veterans-affairs/events",
            "hooks_url": "https://api.github.com/orgs/department-of-veterans-affairs/hooks",
            "issues_url": "https://api.github.com/orgs/department-of-veterans-affairs/issues",
            "members_url": "https://api.github.com/orgs/department-of-veterans-affairs/members/someuser",
            "public_members_url": "https://api.github.com/orgs/department-of-veterans-affairs/public_members/someuser",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "description": "Some organization"
        },
        "user": {
            "login": "someuser",
            "id": 1,
            "node_id": "MDQ6VXNlcjE=",
            "avatar_url": "https://github.com/images/error/octocat_happy.gif",
            "gravatar_id": "",
            "url": "https://api.github.com/users/someuser",
            "html_url": "https://github.com/someuser",
            "followers_url": "https://api.github.com/users/someuser/followers",
            "following_url": "https://api.github.com/users/someuser/following{/other_user}",
            "gists_url": "https://api.github.com/users/someuser/gists{/gist_id}",
            "starred_url": "https://api.github.com/users/someuser/starred{/owner}{/repo}",
            "subscriptions_url": "https://api.github.com/users/someuser/subscriptions",
            "organizations_url": "https://api.github.com/users/someuser/orgs",
            "repos_url": "https://api.github.com/users/someuser/repos",
            "events_url": "https://api.github.com/users/someuser/events{/privacy}",
            "received_events_url": "https://api.github.com/users/someuser/received_events",
            "type": "User",
            "site_admin": False
        }
    }
    return mocker.Mock(Response, status_code=200, json=mocker.Mock(return_value=github_org_membership))


@pytest.fixture
def success_github_user(mocker):
    github_user = {
        "login": "someuser",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
        "gravatar_id": "",
        "url": "https://api.github.com/users/someuser",
        "html_url": "https://github.com/someuser",
        "followers_url": "https://api.github.com/users/someuser/followers",
        "following_url": "https://api.github.com/users/someuser/following{/other_user}",
        "gists_url": "https://api.github.com/users/someuser/gists{/gist_id}",
        "starred_url": "https://api.github.com/users/someuser/starred{/owner}{/repo}",
        "subscriptions_url": "https://api.github.com/someuser/octocat/subscriptions",
        "organizations_url": "https://api.github.com/someuser/octocat/orgs",
        "repos_url": "https://api.github.com/users/someuser/repos",
        "events_url": "https://api.github.com/users/someuser/events{/privacy}",
        "received_events_url": "https://api.github.com/users/someuser/received_events",
        "type": "User",
        "site_admin": False,
        "name": "monalisa someuser",
        "company": "GitHub",
        "blog": "https://github.com/blog",
        "location": "San Francisco",
        "email": "octocat@github.com",
        "hireable": False,
        "bio": "There once was...",
        "twitter_username": "monatheoctocat",
        "public_repos": 2,
        "public_gists": 1,
        "followers": 20,
        "following": 0,
        "created_at": "2008-01-14T04:33:35Z",
        "updated_at": "2008-01-14T04:33:35Z",
        "private_gists": 81,
        "total_private_repos": 100,
        "owned_private_repos": 100,
        "disk_usage": 10000,
        "collaborators": 8,
        "two_factor_authentication": True,
        "plan": {
            "name": "Medium",
            "space": 400,
            "private_repos": 20,
            "collaborators": 0
        }
    }
    return mocker.Mock(Response, status_code=200, json=mocker.Mock(return_value=github_user))


@pytest.fixture
def success_github_user_emails(mocker):
    github_user_emails = [
        {
            "email": "some.user@thoughtworks.com",
            "verified": True,
            "primary": True,
            "visibility": "public"
        }
    ]
    return mocker.Mock(Response, json=mocker.Mock(return_value=github_user_emails))


@pytest.fixture
def github_data(mocker, success_github_org_membership, success_github_user, success_github_user_emails):
    mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token')
    mocker.patch(
        'app.oauth.rest.make_github_get_request',
        side_effect=[success_github_org_membership, success_github_user_emails, success_github_user])

    email = success_github_user_emails.json()[0].get('email')
    identity_provider_user_id = success_github_org_membership.json().get("user").get("id")
    name = success_github_user.json().get('name')

    return email, identity_provider_user_id, name


class TestLogin:

    def test_should_return_501_if_toggle_is_disabled(self, client, github_login_toggle_disabled):
        response = client.get('/auth/login')

        assert response.status_code == 501

    def test_should_redirect_to_github_if_toggle_is_enabled(
            self, client, github_login_toggle_enabled, identity_provider_authorization_url
    ):
        response = client.get('/auth/login')

        assert response.status_code == 302
        assert identity_provider_authorization_url in response.location


class TestAuthorize:

    def test_should_return_501_if_toggle_is_disabled(self, client, github_login_toggle_disabled):
        response = client.get('/auth/authorize')

        assert response.status_code == 501

    @pytest.mark.parametrize('exception', [OAuthException, HTTPError])
    def test_should_redirect_to_login_failure_if_organization_membership_verification_or_user_info_retrieval_fails(
            self, client, notify_api, github_login_toggle_enabled, mocker, cookie_config,
            exception
    ):
        mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token')
        mock_logger = mocker.patch('app.oauth.rest.current_app.logger.error')
        mocker.patch(
            'app.oauth.rest.make_github_get_request',
            side_effect=exception
        )

        with set_config_values(notify_api, cookie_config):
            response = client.get('/auth/authorize')

        assert response.status_code == 302
        assert f"{cookie_config['UI_HOST_NAME']}/login/failure" in response.location
        assert not any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME'] for cookie in client.cookie_jar
        )
        mock_logger.assert_called_once()

    def test_should_redirect_to_login_failure_if_incorrect_github_id(
            self, client, notify_api, github_login_toggle_enabled, mocker, cookie_config, github_data
    ):
        mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token')
        mocker.patch('app.oauth.rest.create_access_token', return_value='some-access-token-value')
        mocker.patch('app.oauth.rest.create_or_retrieve_user', side_effect=IncorrectGithubIdException)
        mock_logger = mocker.patch('app.oauth.rest.current_app.logger.error')

        with set_config_values(notify_api, cookie_config):
            response = client.get('/auth/authorize')

        assert response.status_code == 302
        assert f"{cookie_config['UI_HOST_NAME']}/login/failure" in response.location
        assert not any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME'] for cookie in client.cookie_jar
        )
        mock_logger.assert_called_once()

    def test_should_redirect_to_login_denied_if_user_denies_access(
            self, client, notify_api, github_login_toggle_enabled, mocker, cookie_config, github_data
    ):
        mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token', side_effect=OAuthError)
        mock_logger = mocker.patch('app.oauth.rest.current_app.logger.error')

        with set_config_values(notify_api, cookie_config):
            response = client.get('/auth/authorize')

        assert response.status_code == 302
        assert f"{cookie_config['UI_HOST_NAME']}/login/failure?denied_authorization" in response.location
        assert not any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME'] for cookie in client.cookie_jar
        )
        mock_logger.assert_called_once()

    def test_should_raise_exception_if_304_from_github_get(
            self, client, notify_api, github_login_toggle_enabled, mocker
    ):
        github_access_token = mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token')
        github_get_user_resp = mocker.Mock(Response, status_code=304)

        mocker.patch(
            'app.oauth.rest.oauth_registry.github.get',
            return_value=github_get_user_resp,
        )

        with pytest.raises(OAuthException):
            make_github_get_request('/user', github_access_token)

    @pytest.mark.parametrize('status_code', [403, 404])
    def test_should_raise_http_error_if_error_from_github_get(
            self, client, notify_api, github_login_toggle_enabled, mocker, status_code
    ):
        github_access_token = mocker.patch('app.oauth.rest.oauth_registry.github.authorize_access_token')
        github_get_user_resp = mocker.Mock(Response, status_code=status_code)

        mocker.patch(
            'app.oauth.rest.oauth_registry.github.get',
            return_value=github_get_user_resp,
        )

        with pytest.raises(OAuthException) as e:
            make_github_get_request('/user', github_access_token)

        assert e.value.status_code == 401
        assert e.value.message == 'User Account not found.'

    def test_should_redirect_to_ui_if_user_is_member_of_va_organization(
            self, client, notify_api, github_login_toggle_enabled, mocker, cookie_config, github_data
    ):
        found_user = User()
        mocker.patch('app.oauth.rest.create_or_retrieve_user', return_value=found_user)
        create_access_token = mocker.patch('app.oauth.rest.create_access_token', return_value='some-access-token-value')

        with set_config_values(notify_api, cookie_config):
            response = client.get('/auth/authorize')

        create_access_token.assert_called_with(identity=found_user.serialize_for_user_services())

        assert response.status_code == 302
        assert response.location == f"{cookie_config['UI_HOST_NAME']}/login/success"

        assert any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME']
            and cookie.value == 'some-access-token-value'
            for cookie in client.cookie_jar
        )

    @pytest.mark.parametrize('identity_provider_user_id', [None, '1'])
    def test_should_create_or_update_existing_user_with_identity_provider_user_id_when_successfully_verified(
            self, client, notify_api, github_login_toggle_enabled, mocker, cookie_config, github_data,
            identity_provider_user_id
    ):
        expected_email, expected_user_id, expected_name = github_data

        found_user = User(
            email_address=expected_email,
            identity_provider_user_id=identity_provider_user_id,
            name=expected_name
        )
        create_or_retrieve_user = mocker.patch(
            'app.oauth.rest.create_or_retrieve_user', return_value=found_user
        )

        mocker.patch('app.oauth.rest.create_access_token', return_value='some-access-token-value')

        with set_config_values(notify_api, cookie_config):
            client.get('/auth/authorize')

        create_or_retrieve_user.assert_called_with(
            email_address=expected_email,
            identity_provider_user_id=expected_user_id,
            name=expected_name)


class TestRedeemToken:

    def test_should_return_501_if_toggle_is_disabled(self, client, github_login_toggle_disabled):
        response = client.get('/auth/redeem-token')

        assert response.status_code == 501

    @pytest.mark.parametrize('exception', [NoAuthorizationError, ExpiredSignatureError])
    def test_should_return_401_if_cookie_verification_fails(
            self, client, github_login_toggle_enabled, mocker, exception
    ):
        mocker.patch('app.oauth.rest.verify_jwt_in_request', side_effect=exception)
        response = client.get('/auth/redeem-token')

        assert response.status_code == 401

    def test_should_return_cookie_in_body(
            self, client, github_login_toggle_enabled, mocker, notify_api, cookie_config
    ):
        mocker.patch('app.oauth.rest.verify_jwt_in_request', side_effect=None)

        expected_cookie_value = 'some-cookie-value'
        client.set_cookie('test',
                          cookie_config['JWT_ACCESS_COOKIE_NAME'],
                          expected_cookie_value)

        with set_config_values(notify_api,
                               {'JWT_ACCESS_COOKIE_NAME': cookie_config['JWT_ACCESS_COOKIE_NAME']}
                               ):
            response = client.get('/auth/redeem-token')

        assert response.status_code == 200
        assert response.json.get('data') == expected_cookie_value

    def test_should_set_cors_headers(self, client, github_login_toggle_enabled, mocker, notify_api, cookie_config):
        mocker.patch('app.oauth.rest.verify_jwt_in_request', side_effect=None)

        with set_config_values(notify_api, {
            'UI_HOST_NAME': cookie_config['UI_HOST_NAME']
        }):
            response = client.get('/auth/redeem-token')

        assert response.access_control_allow_credentials
        assert response.access_control_allow_origin == cookie_config['UI_HOST_NAME']


class TestLoginWithPassword:

    def test_login_with_password_succeeds_when_correct_credentials(
            self, notify_api, client, login_with_password_toggle_enabled, mocker
    ):
        some_p = 'sillypassword'
        user = User()
        user.password = some_p
        mocker.patch('app.oauth.rest.get_user_by_email', return_value=user)
        data = {
            "email_address": "dummy@email.address",
            "password": some_p
        }

        response = client.post('/auth/login', data=json.dumps(data), headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200

    def test_should_return_501_if_password_toggle_is_disabled(self, client, login_with_password_toggle_disabled):
        response = client.post('/auth/login')

        assert response.status_code == 501

    def test_should_return_400_when_email_address_or_password_not_present_in_body(
            self, client, login_with_password_toggle_enabled
    ):
        data = {}

        response = client.post('/auth/login', data=json.dumps(data), headers=[('Content-Type', 'application/json')])
        assert response.status_code == 400

    def test_should_return_401_when_wrong_password(
            self, client, login_with_password_toggle_enabled, mocker
    ):
        some_t = 'wrong'
        some_p = 'silly-me'
        user = User()
        user.password = some_p
        mocker.patch('app.oauth.rest.get_user_by_email', return_value=user)
        credentials = {
            "email_address": "some@email.address",
            "password": some_t
        }

        response = client.post(
            '/auth/login',
            data=json.dumps(credentials),
            headers=[('Content-Type', 'application/json')]
        )
        assert response.status_code == 401

    def test_should_return_401_when_user_not_found_by__email_address(
            self, client, login_with_password_toggle_enabled, mocker
    ):
        some_p = 'silly-me'
        user = User()
        user.password = some_p
        mocker.patch('app.oauth.rest.get_user_by_email', side_effect=NoResultFound)
        credentials = {
            "email_address": "some@email.address",
            "password": some_p
        }

        response = client.post(
            '/auth/login',
            data=json.dumps(credentials),
            headers=[('Content-Type', 'application/json')]
        )
        assert response.status_code == 401

    def test_login_with_password_success_returns_token(
            self, notify_api, client, login_with_password_toggle_enabled, fake_uuid, mocker
    ):
        some_p = 'sillypassword'
        email_address = 'success@email.address'
        user = User()
        user.id = fake_uuid
        user.email_address = email_address
        user.password = some_p
        mocker.patch('app.oauth.rest.get_user_by_email', return_value=user)
        data = {
            "email_address": email_address,
            "password": some_p
        }

        response = client.post('/auth/login', data=json.dumps(data), headers=[('Content-Type', 'application/json')])
        response_json = response.json
        assert response_json['result'] == 'success'
        assert response_json['token'] is not None


class TestLogout:

    def test_should_return_501_if_toggle_is_disabled(self, client, github_login_toggle_disabled):
        response = client.get('/auth/logout')

        assert response.status_code == 501

    def test_should_redirect_to_ui_and_clear_cookies(
            self, client, github_login_toggle_enabled, notify_api, cookie_config, github_data, db_session
    ):
        with set_config_values(notify_api, cookie_config):
            client.get('/auth/authorize')

        assert any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME']
            for cookie in client.cookie_jar
        )

        with set_config_values(notify_api, cookie_config):
            response = client.get('/auth/logout')

        assert response.status_code == 302
        assert cookie_config['UI_HOST_NAME'] in response.location

        assert not any(
            cookie.name == cookie_config['JWT_ACCESS_COOKIE_NAME']
            for cookie in client.cookie_jar
        )
