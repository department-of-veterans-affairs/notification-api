from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm.exc import NoResultFound

from app.constants import KEY_TYPE_NORMAL
from app.dao.api_key_dao import (
    get_model_api_key,
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secrets,
    get_unsigned_secret,
    expire_api_key,
)
from app.models import ApiKey, Service


def test_save_api_key_should_create_new_api_key_and_history(notify_db_session, sample_service):
    service = sample_service()
    api_key = ApiKey(
        **{'service': service, 'name': service.name, 'created_by': service.created_by, 'key_type': KEY_TYPE_NORMAL}
    )
    save_model_api_key(api_key)

    ApiKeyHistory = ApiKey.get_history_model()

    try:
        assert api_key.version == 1

        stmt = select(ApiKeyHistory).where(ApiKeyHistory.id == api_key.id)
        history = notify_db_session.session.scalars(stmt).one()

        assert history.version == api_key.version
    finally:
        # Teardown
        # Clear API Key history
        stmt = delete(ApiKeyHistory).where(ApiKeyHistory.id == api_key.id)
        notify_db_session.session.execute(stmt)

        # Clear API Key
        stmt = delete(ApiKey).where(ApiKey.id == api_key.id)
        notify_db_session.session.execute(stmt)
        notify_db_session.session.commit()


def test_expire_api_key_should_update_the_api_key_and_create_history_record(
    notify_db_session,
    sample_api_key,
):
    api_key = sample_api_key()
    assert api_key.expiry_date > datetime.utcnow()
    assert not api_key.revoked

    ApiKeyHistory = ApiKey.get_history_model()
    stmt = select(func.count()).select_from(ApiKeyHistory).where(ApiKeyHistory.id == api_key.id)
    assert notify_db_session.session.scalar(stmt) == 1

    expire_api_key(service_id=api_key.service_id, api_key_id=api_key.id)

    notify_db_session.session.refresh(api_key)
    assert api_key.expiry_date <= datetime.utcnow(), 'The API key should be expired.'
    assert api_key.revoked, 'The API key should have revoked=True when expired.'
    assert notify_db_session.session.scalar(stmt) == 2, 'Should have created a new history row'


def test_get_api_key_should_raise_exception_when_api_key_does_not_exist(sample_service, fake_uuid):
    with pytest.raises(NoResultFound):
        get_model_api_key(fake_uuid)


def test_get_api_keys_should_raise_exception_when_api_key_does_not_exist(sample_service, fake_uuid):
    with pytest.raises(NoResultFound):
        print(get_model_api_keys(sample_service().id))


def test_should_return_api_keys_for_service(sample_api_key):
    api_key1 = sample_api_key()
    api_key2 = get_model_api_keys(service_id=api_key1.service_id)
    assert len(api_key2) == 1
    assert api_key2[0] == api_key1


def test_should_return_api_key_for_id(sample_api_key):
    api_key1 = sample_api_key()
    api_key2 = get_model_api_key(key_id=api_key1.id)
    assert api_key2 == api_key1


def test_should_return_api_key_for_id_when_revoked(sample_api_key):
    api_key1 = sample_api_key(expired=True)
    api_key2 = get_model_api_key(key_id=api_key1.id)
    assert api_key2 == api_key1


def test_should_return_unsigned_api_keys_for_service_id(sample_api_key):
    api_key = sample_api_key()
    unsigned_api_key = get_unsigned_secrets(api_key.service_id)
    assert len(unsigned_api_key) == 1
    assert api_key._secret != unsigned_api_key[0]
    assert unsigned_api_key[0] == api_key.secret


def test_get_unsigned_secret_returns_key(sample_api_key):
    api_key = sample_api_key()
    unsigned_api_key = get_unsigned_secret(api_key.id)
    assert api_key._secret != unsigned_api_key
    assert unsigned_api_key == api_key.secret


def test_save_api_key_can_create_keys_with_same_name(
    notify_db_session,
    sample_api_key,
    sample_service,
) -> None:
    service = sample_service()

    # Create an expired API key.
    sample_api_key(
        service=service,
        key_name='normal api key',
        expired=True,
    )

    # Create an API key with the same name that is not expired
    sample_api_key(
        service=service,
        key_name='normal api key',
        expired=False,
    )

    api_key = ApiKey(
        service=service,
        name='normal api key',
        created_by=service.created_by,
        key_type=KEY_TYPE_NORMAL,
        expiry_date=datetime.utcnow() + timedelta(days=180),
    )

    # Adding a key with the same name should not raise IntegrityError. They will have unique IDs and secrets.
    save_model_api_key(api_key)

    api_keys = get_model_api_keys(service.id)

    # ensure there are 2 keys
    assert len(api_keys) == 2
    # ensure they have unique ids
    assert len(set([key.id for key in api_keys])) == 2
    # ensure the names are the same
    assert len(set([key.name for key in api_keys])) == 1

    try:
        assert api_key.expiry_date > datetime.utcnow(), 'The key should not be expired.'
        assert not api_key.revoked, 'The key should not be revoked.'
    finally:
        # Teardown
        # Clear API Key history
        ApiKeyHistory = ApiKey.get_history_model()
        stmt = delete(ApiKeyHistory).where(ApiKeyHistory.id == api_key.id)
        notify_db_session.session.execute(stmt)

        # Clear API Key
        stmt = delete(ApiKey).where(ApiKey.id == api_key.id)
        notify_db_session.session.execute(stmt)
        notify_db_session.session.commit()


def test_save_api_key_should_not_create_new_service_history(
    notify_db_session,
    sample_service,
):
    service = sample_service()

    service_history_model = Service.get_history_model()
    stmt_service = select(func.count()).select_from(service_history_model).where(service_history_model.id == service.id)

    assert notify_db_session.session.scalar(stmt_service) == 1

    api_key = ApiKey(
        **{'service': service, 'name': service.name, 'created_by': service.created_by, 'key_type': KEY_TYPE_NORMAL}
    )

    save_model_api_key(api_key)

    ApiKeyHistory = ApiKey.get_history_model()
    stmt_api_key = select(func.count()).select_from(ApiKeyHistory).where(ApiKeyHistory.id == api_key.id)

    assert notify_db_session.session.scalar(stmt_service) == 1, 'No new Service history'
    assert notify_db_session.session.scalar(stmt_api_key) == 1, 'Only one ApiKey history'


def test_save_api_key_should_generate_secret_with_expected_format(sample_service):
    service = sample_service()
    api_key = ApiKey(
        **{'service': service, 'name': service.name, 'created_by': service.created_by, 'key_type': KEY_TYPE_NORMAL}
    )
    save_model_api_key(api_key)

    assert api_key.secret is not None
    assert len(api_key.secret) >= 86
