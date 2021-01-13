import uuid

from app.service.service_providers import is_provider_valid


def test_check_provider_exists(notify_db):
    provider_id = uuid.uuid4()

    assert is_provider_valid(provider_id, 'email') is False
