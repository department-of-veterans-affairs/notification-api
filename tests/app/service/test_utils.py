import pytest

from app.service.utils import compute_source_email_address, compute_source_email_address_with_display_name
from tests.conftest import set_config_values

DEFAULT_EMAIL_FROM_VALUES = {
    'NOTIFY_EMAIL_FROM_DOMAIN': 'default.domain',
    'NOTIFY_EMAIL_FROM_USER': 'default-email-from',
    'NOTIFY_EMAIL_FROM_NAME': 'Default Name',
}


@pytest.mark.parametrize(
    f'service_sending_domain, service_email_from, provider_from_domain, provider_from_user'
    f'expected_source_email_address',
    [
        (None, None, None, None, 'default-email-from@default.domain'),
        ('custom.domain', None, None, None, 'default-email-from@custom.domain'),
        (None, 'custom-email-from', None, None, 'custom-email-from@default.domain'),
        (None, None, 'provider.domain', 'provider-from-user', 'provider-from-user@provider.domain'),
        ('custom.domain', 'custom-email-from', 'provider.domain', 'provider-from-user',
         'custom-email-from@custom.domain')
    ]
)
def test_should_compute_source_email_address(
        sample_service,
        notify_api,
        test_email_client,
        service_sending_domain,
        service_email_from,
        provider_from_domain,
        provider_from_user,
        expected_source_email_address
):
    sample_service.sending_domain = service_sending_domain
    sample_service.email_from = service_email_from
    test_email_client.init(provider_from_domain, provider_from_user)

    with set_config_values(notify_api, DEFAULT_EMAIL_FROM_VALUES):
        assert compute_source_email_address(sample_service, test_email_client) == expected_source_email_address


def test_should_compute_source_email_address_with_display_name(
        sample_service,
        notify_api,
        mocker
):
    mocker.patch('app.service.utils.compute_source_email_address', return_value='some@email.com')

    with set_config_values(notify_api, DEFAULT_EMAIL_FROM_VALUES):
        assert compute_source_email_address_with_display_name(sample_service) == '"Default Name" <some@email.com>'
