from random import randint

import pytest
from sqlalchemy import delete
import base64

from app.models import VAProfileLocalCache
from lambda_functions.va_profile.va_profile_opt_in_out_lambda import EncryptedVAProfileId


# Helpers
def generate_base64_test_key(value: str) -> str:
    """Generates the base64 encoding of the input string value.

    Note: This generates constant test key(s) for consistent encryption/decryption during tests
    Using a fixed test key - this is only for testing and not a real secret
    """
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')


# PII encryption test setup
TEST_ENCRYPTION_KEY = generate_base64_test_key('This is an 32 byte key for tests')
TEST_HMAC_KEY = generate_base64_test_key('This is a second 32 byte key for HMAC tests')


@pytest.fixture
def mock_pii_env_vars(monkeypatch):
    monkeypatch.setenv('PII_ENCRYPTION_KEY_PATH', '/fake/path/to/pii_encryption_key')
    monkeypatch.setenv('PII_ENCRYPTION_KEY', TEST_ENCRYPTION_KEY)
    monkeypatch.setenv('PII_HMAC_KEY', TEST_HMAC_KEY)


@pytest.fixture
def sample_va_profile_local_cache(notify_db_session, mock_pii_env_vars):
    created_va_profile_local_cache_ids = []

    def _sample_va_profile_local_cache(
        source_datetime: str,
        allowed: bool = True,
        va_profile_id: int | None = None,
        communication_item_id: int = 5,
        communication_channel_id: int = 1,
    ):
        """
        The combination of va_profile_id, communication_item_id, and communication_channel_id must be unique.
        """
        va_profile_id: int = va_profile_id if va_profile_id else randint(1000, 100000)
        encrypted_va_profile_id: EncryptedVAProfileId = EncryptedVAProfileId(va_profile_id)

        va_profile_local_cache = VAProfileLocalCache(
            allowed=allowed,
            va_profile_id=encrypted_va_profile_id.get_pii(),
            encrypted_va_profile_id=encrypted_va_profile_id.fernet_encryption,
            encrypted_va_profile_id_blind_index=encrypted_va_profile_id.hmac_encryption,
            communication_item_id=communication_item_id,
            communication_channel_id=communication_channel_id,
            source_datetime=source_datetime,
        )

        notify_db_session.session.add(va_profile_local_cache)
        notify_db_session.session.commit()
        created_va_profile_local_cache_ids.append(va_profile_local_cache.id)
        return va_profile_local_cache

    yield _sample_va_profile_local_cache

    # Teardown
    stmt = delete(VAProfileLocalCache).where(VAProfileLocalCache.id.in_(created_va_profile_local_cache_ids))
    notify_db_session.session.execute(stmt)
    notify_db_session.session.commit()
