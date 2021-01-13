import uuid

from app.models import ProviderDetails
from app.service.service_providers import is_provider_valid


def test_check_provider_exists(notify_db):
    provider_id = uuid.uuid4()

    assert is_provider_valid(provider_id, 'email') is False


def test_check_provider_is_active(mocker):
    mocked_provider_details = mocker.Mock(ProviderDetails)
    mocked_provider_details.active = False
    mocker.patch(
        'app.service.service_providers.get_provider_details_by_id',
        return_value=[mocked_provider_details]
    )
    assert is_provider_valid(uuid.uuid4(), 'email') is False
