import uuid

from app.models import ProviderDetails, EMAIL_TYPE, SMS_TYPE
from app.service.service_providers import is_provider_valid

PROVIDER_DETAILS_BY_ID_PATH = 'app.service.service_providers.get_provider_details_by_id'


def test_check_provider_exists(notify_db):
    provider_id = uuid.uuid4()

    assert is_provider_valid(provider_id, 'email') is False


def test_check_provider_is_active_and_of_incorrect_type(mocker):
    mocked_provider_details = mocker.Mock(ProviderDetails)
    mocked_provider_details.active = True
    mocked_provider_details.notification_type = SMS_TYPE
    mocker.patch(
        PROVIDER_DETAILS_BY_ID_PATH,
        return_value=mocked_provider_details
    )
    assert is_provider_valid(uuid.uuid4(), EMAIL_TYPE) is False


def test_check_provider_is_inactive_and_of_correct_type(mocker):
    mocked_provider_details = mocker.Mock(ProviderDetails)
    mocked_provider_details.active = False
    mocked_provider_details.notification_type = EMAIL_TYPE
    mocker.patch(
        PROVIDER_DETAILS_BY_ID_PATH,
        return_value=mocked_provider_details
    )
    assert is_provider_valid(uuid.uuid4(), EMAIL_TYPE) is False


def test_check_provider_is_active_and_of_correct_type(mocker):
    mocked_provider_details = mocker.Mock(ProviderDetails)
    mocked_provider_details.active = True
    mocked_provider_details.notification_type = EMAIL_TYPE
    mocker.patch(
        'app.service.service_providers.get_provider_details_by_id',
        return_value=mocked_provider_details
    )
    assert is_provider_valid(uuid.uuid4(), EMAIL_TYPE) is True
