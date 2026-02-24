from random import randint
from typing import Optional

import pytest
from sqlalchemy import delete
import base64

from app.models import VAProfileLocalCache
from lambda_functions.va_profile.va_profile_opt_in_out_lambda import EncryptedVAProfileId
from unittest.mock import Mock, patch


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
        va_profile_id: Optional[int] = None,
        communication_item_id: int = 5,
        communication_channel_id: int = 1,
    ):
        """
        The combination of va_profile_id, communication_item_id, and communication_channel_id must be unique.
        """
        encrypted_vap_id: EncryptedVAProfileId = EncryptedVAProfileId(
            va_profile_id if va_profile_id is not None else randint(1000, 100000)
        )

        va_profile_local_cache = VAProfileLocalCache(
            allowed=allowed,
            va_profile_id=encrypted_vap_id.get_pii(),
            encrypted_va_profile_id=encrypted_vap_id.fernet_encryption,
            encrypted_va_profile_id_blind_index=encrypted_vap_id.hmac_encryption,
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


@pytest.fixture
def mock_lambda_db_connection(notify_db_session):
    raw_conn = notify_db_session.session.connection().connection.driver_connection
    with patch('lambda_functions.va_profile.va_profile_opt_in_out_lambda.db_connection', raw_conn):
        yield raw_conn


@pytest.fixture
def patch_https():
    """Factory fixture that patches HTTPSConnection and returns (mock_put, mock_post)."""

    def _patch_https(
        put_status=200,
        post_status=201,
        post_body=b'{"id":"e7b8cdda-858e-4b6f-a7df-93a71a2edb1e"}',
    ):
        mock_put = Mock()
        mock_put_response = Mock()
        mock_put_response.status = put_status
        mock_put_response.headers = {'Content-Type': 'application/json'}
        mock_put_response.read.return_value = b'{"dateTime":"2022-04-07T19:37:59.320Z","status":"COMPLETED_SUCCESS"}'
        mock_put.getresponse.return_value = mock_put_response

        mock_post = Mock()
        mock_post_response = Mock()
        mock_post_response.status = post_status
        mock_post_response.read.return_value = post_body
        mock_post.getresponse.return_value = mock_post_response

        patch(
            'lambda_functions.va_profile.va_profile_opt_in_out_lambda.HTTPSConnection',
            side_effect=[mock_put, mock_post],
        ).start()

        return mock_put, mock_post

    return _patch_https
