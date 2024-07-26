import json
import pytest


from app.va.va_profile import (
    VAProfileClient,
)
from app.models import RecipientIdentifier
from app.va.identifier import IdentifierType, transform_to_fhir_format, OIDS


MOCK_VA_PROFILE_URL = 'http://mock.vaprofile.va.gov/'


@pytest.fixture(scope='function')
def test_va_profile_client(mocker, notify_api):
    with notify_api.app_context():
        mock_logger = mocker.Mock()
        mock_ssl_key_path = 'some_key.pem'
        mock_ssl_cert_path = 'some_cert.pem'
        mock_statsd_client = mocker.Mock()

        test_va_profile_client = VAProfileClient()
        test_va_profile_client.init_app(
            mock_logger, MOCK_VA_PROFILE_URL, mock_ssl_cert_path, mock_ssl_key_path, mock_statsd_client
        )

        return test_va_profile_client


@pytest.fixture(scope='module')
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


def test_retrieve_email_from_profile_v3(
    rmock, test_va_profile_client, mock_response, recipient_identifier, id_with_aaid, oid
):
    url = f'{MOCK_VA_PROFILE_URL}profile/v3/{oid}/{id_with_aaid}'
    rmock.post(url, json=mock_response, status_code=200)

    email = test_va_profile_client.get_email_from_profile_v3(recipient_identifier)

    assert email == mock_response['profile']['contactInformation']['emails'][0]['emailAddressText']
    assert rmock.called


def test_retrieve_telephone_from_profile_v3(
    rmock, test_va_profile_client, mock_response, recipient_identifier, id_with_aaid, oid
):
    url = f'{MOCK_VA_PROFILE_URL}profile/v3/{oid}/{id_with_aaid}'
    rmock.post(url, json=mock_response, status_code=200)

    telephone = test_va_profile_client.get_telephone_from_profile_v3(recipient_identifier)

    assert telephone is not None
    assert rmock.called
