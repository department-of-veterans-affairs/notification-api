import json
from urllib import parse
from unittest.mock import PropertyMock

import pytest
import requests
import requests_mock

from app.feature_flags import FeatureFlag
from app.models import EMAIL_TYPE, RecipientIdentifier
from app.va.identifier import IdentifierType, OIDS, transform_to_fhir_format
from app.va.va_profile import VAProfileClient
from app.va.va_profile.exceptions import (
    NoContactInfoException,
    VAProfileIDNotFoundException,
    VAProfileNonRetryableException,
    VAProfileRetryableException,
)
from app.va.va_profile.va_profile_client import CommunicationChannel

from tests.app.factories.feature_flag import mock_feature_flag

MOCK_VA_PROFILE_URL = 'http://mock.vaprofile.va.gov'


@pytest.fixture(scope='function')
def mock_va_profile_client(mocker, notify_api):
    with notify_api.app_context():
        mock_logger = mocker.Mock()
        mock_ssl_key_path = 'some_key.pem'
        mock_ssl_cert_path = 'some_cert.pem'
        mock_statsd_client = mocker.Mock()
        mock_va_profile_token = mocker.Mock()

        client = VAProfileClient()
        client.init_app(
            logger=mock_logger,
            va_profile_url=MOCK_VA_PROFILE_URL,
            ssl_cert_path=mock_ssl_cert_path,
            ssl_key_path=mock_ssl_key_path,
            va_profile_token=mock_va_profile_token,
            statsd_client=mock_statsd_client,
        )

        return client


@pytest.fixture(scope='function')
def mock_response():
    with open('tests/app/va/va_profile/mock_response.json', 'r') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def recipient_identifier():
    return RecipientIdentifier(notification_id='123456', id_type=IdentifierType.VA_PROFILE_ID, id_value='1234')


@pytest.fixture(scope='module')
def id_with_aaid(recipient_identifier):
    return transform_to_fhir_format(recipient_identifier)


@pytest.fixture(scope='module')
def oid(recipient_identifier):
    return OIDS.get(recipient_identifier.id_type)


@pytest.fixture(scope='module')
def url(oid, id_with_aaid):
    return f'{MOCK_VA_PROFILE_URL}/profile-service/profile/v3/{oid}/{id_with_aaid}'


class TestVAProfileClient:
    def test_ut_get_email_calls_endpoint_and_returns_email_address(
        self, rmock, mock_va_profile_client, mock_response, recipient_identifier, url, mocker, sample_email_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(url, json=mock_response, status_code=200)

        result = mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_email_notification)
        email = result.recipient

        assert email == mock_response['profile']['contactInformation']['emails'][0]['emailAddressText']
        assert rmock.called

    def test_ut_get_email_raises_NoContactInfoException_if_no_emails_exist(
        self, rmock, mock_va_profile_client, mock_response, recipient_identifier, url, mocker, sample_email_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        mock_response['profile']['contactInformation']['emails'] = []
        rmock.post(url, json=mock_response, status_code=200)

        with pytest.raises(NoContactInfoException):
            mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_email_notification)

    def test_ut_get_profile_calls_correct_url(
        self,
        rmock,
        mock_va_profile_client,
        mock_response,
        recipient_identifier,
        url,
        id_with_aaid,
        oid,
        mocker,
        sample_sms_notification,
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(url, json=mock_response, status_code=200)

        mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_sms_notification)

        assert rmock.called

        escaped_id = parse.quote(id_with_aaid, safe='')
        expected_url = f'{MOCK_VA_PROFILE_URL}/profile-service/profile/v3/{oid}/{escaped_id}'

        assert rmock.request_history[0].url == expected_url

    def test_ut_get_email_raises_exception_when_failed_request(
        self, rmock, mock_va_profile_client, recipient_identifier, url, mocker, sample_email_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        response = {
            'messages': [
                {
                    'code': 'CORE103',
                    'key': '_CUF_NOT_FOUND',
                    'text': 'The ContactInformationBio for id/criteria 103 could not be found. Please correct your requ...',
                    'severity': 'INFO',
                }
            ],
            'txAuditId': 'dca32cae-b410-46c5-b61b-9a382567843f',
            'status': 'COMPLETED_FAILURE',
        }
        rmock.post(url, json=response, status_code=200)

        with pytest.raises(VAProfileNonRetryableException):
            mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_email_notification)

    def test_ut_get_telephone_calls_endpoint_and_returns_phone_number(
        self, rmock, mock_va_profile_client, mock_response, recipient_identifier, url, mocker, sample_sms_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(url, json=mock_response, status_code=200)

        result = mock_va_profile_client.get_telephone_with_permission(recipient_identifier, sample_sms_notification)
        telephone = result.recipient

        assert telephone is not None
        assert rmock.called


class TestVAProfileClientExceptionHandling:
    def test_ut_get_telephone_raises_NoContactInfoException_if_no_telephones_exist(
        self, rmock, mock_va_profile_client, mock_response, recipient_identifier, url, mocker, sample_sms_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        mock_response['profile']['contactInformation']['telephones'] = []
        rmock.post(url, json=mock_response, status_code=200)

        with pytest.raises(NoContactInfoException):
            mock_va_profile_client.get_telephone_with_permission(recipient_identifier, sample_sms_notification)

    def test_ut_get_telephone_raises_NoContactInfoException_if_no_mobile_telephones_exist(
        self, rmock, mock_va_profile_client, mock_response, recipient_identifier, url, mocker, sample_sms_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        telephones = mock_response['profile']['contactInformation']['telephones']
        mock_response['profile']['contactInformation']['telephones'] = [
            telephone for telephone in telephones if telephone['phoneType'] != 'MOBILE'
        ]
        rmock.post(url, json=mock_response, status_code=200)

        with pytest.raises(NoContactInfoException):
            mock_va_profile_client.get_telephone_with_permission(recipient_identifier, sample_sms_notification)

    def test_ut_handle_exceptions_retryable_exception(self, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        # This test checks if VAProfileRetryableException is raised for a RequestException
        with pytest.raises(VAProfileRetryableException):
            mock_va_profile_client._handle_exceptions('some_va_profile_id', requests.RequestException())

    def test_ut_handle_exceptions_id_not_found_exception(self, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        # Simulate a 404 HTTP error
        error = requests.HTTPError(response=requests.Response())
        error.response.status_code = 404
        # This test checks if VAProfileIDNotFoundException is raised for a 404 error
        with pytest.raises(VAProfileIDNotFoundException):
            mock_va_profile_client._handle_exceptions('some_va_profile_id', error)

    def test_ut_handle_exceptions_non_retryable_exception(self, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        # Simulate a 400 HTTP error
        error = requests.HTTPError(response=requests.Response())
        error.response.status_code = 400
        # This test checks if VAProfileNonRetryableException is raised for a 400 error
        with pytest.raises(VAProfileNonRetryableException):
            mock_va_profile_client._handle_exceptions('some_va_profile_id', error)

    def test_ut_handle_exceptions_timeout_exception(self, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        # This test checks if VAProfileRetryableExcception is raised for a Timeout exception
        # Timeout inherits from requests.RequestException, so all exceptions of type RequestException should
        # raise a VAProfileRetryableException
        with pytest.raises(VAProfileRetryableException):
            mock_va_profile_client._handle_exceptions('some_va_profile_id', requests.Timeout())

    @pytest.mark.parametrize('status', [429, 500])
    def test_ut_client_raises_retryable_exception(
        self,
        rmock,
        mock_va_profile_client,
        recipient_identifier,
        status,
        mocker,
        sample_sms_notification,
        sample_email_notification,
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(requests_mock.ANY, status_code=status)

        with pytest.raises(VAProfileRetryableException):
            mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_email_notification)

        with pytest.raises(VAProfileRetryableException):
            mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_sms_notification)

    def test_ut_client_raises_retryable_exception_when_request_exception_is_thrown(
        self, mock_va_profile_client, recipient_identifier, mocker, sample_sms_notification, sample_email_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        with requests_mock.Mocker(real_http=True) as rmock:
            rmock.post(requests_mock.ANY, exc=requests.RequestException)

            with pytest.raises(VAProfileRetryableException):
                mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_email_notification)

            with pytest.raises(VAProfileRetryableException):
                mock_va_profile_client.get_email_with_permission(recipient_identifier, sample_sms_notification)


class TestCommunicationPermissions:
    @pytest.mark.parametrize('expected', [True, False])
    def test_ut_get_is_communication_allowed_returns_whether_permissions_granted_for_sms_communication(
        self, rmock, mock_va_profile_client, mock_response, url, expected, mocker, sample_sms_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        mock_response['profile']['communicationPermissions'][0]['allowed'] = expected
        mock_response['profile']['communicationPermissions'][0]['communicationItemId'] = (
            sample_sms_notification.va_profile_item_id
        )

        allowed = mock_va_profile_client.get_is_communication_allowed_from_profile(
            mock_response['profile'], sample_sms_notification, CommunicationChannel.TEXT
        )

        assert allowed is expected

    @pytest.mark.parametrize('expected', [True, False])
    def test_ut_get_is_communication_allowed_returns_whether_permissions_granted_for_email_communication(
        self, rmock, mock_va_profile_client, mock_response, url, expected, mocker, sample_email_notification
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        mock_response['profile']['communicationPermissions'][1]['allowed'] = expected
        mock_response['profile']['communicationPermissions'][1]['communicationItemId'] = (
            sample_email_notification.va_profile_item_id
        )

        allowed = mock_va_profile_client.get_is_communication_allowed_from_profile(
            mock_response['profile'], sample_email_notification, CommunicationChannel.EMAIL
        )

        assert allowed is expected

    @pytest.mark.parametrize(
        'default_send, user_set, expected',
        [
            # If the user has set a preference, we always go with that and override default_send
            [True, True, True],
            [True, False, False],
            [False, True, True],
            [False, False, False],
            # If the user has not set a preference, go with the default_send
            [True, None, True],
            [False, None, False],
        ],
    )
    @pytest.mark.parametrize('notification_type', [CommunicationChannel.EMAIL, CommunicationChannel.TEXT])
    def test_ut_get_email_or_sms_with_permission_utilizes_default_send(
        self,
        mock_va_profile_client,
        mock_response,
        recipient_identifier,
        sample_sms_notification,
        sample_email_notification,
        default_send,
        user_set,
        expected,
        notification_type,
        mocker,
    ):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        profile = mock_response['profile']

        if notification_type == CommunicationChannel.EMAIL:
            notification = sample_email_notification
        else:
            notification = sample_sms_notification

        mocker.patch.object(type(notification), 'default_send', new_callable=PropertyMock, return_value=default_send)

        if user_set is not None:
            profile['communicationPermissions'][0]['allowed'] = user_set
            profile['communicationPermissions'][0]['communicationItemId'] = notification.va_profile_item_id
            profile['communicationPermissions'][0]['communicationChannelId'] = notification_type.id
        else:
            profile['communicationPermissions'] = []

        mocker.patch.object(mock_va_profile_client, 'get_profile', return_value=profile)

        if notification_type == CommunicationChannel.EMAIL:
            client_fn = mock_va_profile_client.get_email_with_permission
        else:
            client_fn = mock_va_profile_client.get_telephone_with_permission

        result = client_fn(recipient_identifier, notification)
        assert result.communication_allowed == expected


class TestSendEmailStatus:
    mock_response = {}
    mock_notification_data = {
        'id': '2e9e6920-4f6f-4cd5-9e16-fc306fe23867',  # this is the notification id
        'reference': None,
        'to': 'test@email.com',  # this is the recipient's contact info (email)
        'status': 'delivered',  # this will specify the delivery status of the notification
        'status_reason': '',  # populated if there's additional context on the delivery status
        'created_at': '2024-07-25T10:00:00.0',
        'completed_at': '2024-07-25T11:00:00.0',
        'sent_at': '2024-07-25T11:00:00.0',
        'notification_type': EMAIL_TYPE,  # this is the channel/type of notification (email)
        'provider': 'ses',  # email provider
    }

    def test_ut_send_va_profile_email_status_sent_successfully(self, rmock, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(requests_mock.ANY, json=self.mock_response, status_code=200)

        mock_va_profile_client.send_va_profile_email_status(self.mock_notification_data)

        assert rmock.called

        expected_url = f'{MOCK_VA_PROFILE_URL}/contact-information-vanotify/notify/status'
        assert rmock.request_history[0].url == expected_url

    def test_ut_send_va_profile_email_status_timeout(self, rmock, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(requests_mock.ANY, exc=requests.ReadTimeout)

        with pytest.raises(requests.Timeout):
            mock_va_profile_client.send_va_profile_email_status(self.mock_notification_data)

        assert rmock.called

        expected_url = f'{MOCK_VA_PROFILE_URL}/contact-information-vanotify/notify/status'
        assert rmock.request_history[0].url == expected_url

    def test_ut_send_va_profile_email_status_throws_exception(self, rmock, mock_va_profile_client, mocker):
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_COMBINE_CONTACT_INFO_AND_PERMISSIONS_LOOKUP, 'True')
        mock_feature_flag(mocker, FeatureFlag.VA_PROFILE_V3_IDENTIFY_MOBILE_TELEPHONE_NUMBERS, 'True')

        rmock.post(requests_mock.ANY, exc=requests.RequestException)

        with pytest.raises(requests.RequestException):
            mock_va_profile_client.send_va_profile_email_status(self.mock_notification_data)

        assert rmock.called

        expected_url = f'{MOCK_VA_PROFILE_URL}/contact-information-vanotify/notify/status'
        assert rmock.request_history[0].url == expected_url
