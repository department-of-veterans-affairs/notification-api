import pytest
from app.dao.api_key_dao import (
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secrets,
    get_unsigned_secret,
    expire_api_key,
)
from app.models import ApiKey, KEY_TYPE_NORMAL
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound


def test_save_api_key_should_create_new_api_key_and_history(notify_db_session, sample_service):
    service = sample_service()
    api_key = ApiKey(**{
        'service': service,
        'name': service.name,
        'created_by': service.created_by,
        'key_type': KEY_TYPE_NORMAL
    })
    save_model_api_key(api_key)

    all_api_keys = get_model_api_keys(service_id=service.id)

    try:
        assert len(all_api_keys) == 1
        assert all_api_keys[0] == api_key
        assert api_key.version == 1
    except AssertionError:
        # Teardown
        for api_key in all_api_keys:
            notify_db_session.session.delete(api_key)
        notify_db_session.session.commit()
        raise

    all_history = api_key.get_history_model().query.all()

    try:
        assert len(all_history) == 1
        assert all_history[0].id == api_key.id
        assert all_history[0].version == api_key.version
    finally:
        # Teardown
        for api_key_history in all_history:
            notify_db_session.session.delete(api_key_history)
        for api_key in all_api_keys:
            notify_db_session.session.delete(api_key)
        notify_db_session.session.commit()


def test_expire_api_key_should_update_the_api_key_and_create_history_record(sample_api_key):
    api_key = sample_api_key()
    expire_api_key(service_id=api_key.service_id, api_key_id=api_key.id)
    all_api_keys = get_model_api_keys(service_id=api_key.service_id)
    assert len(all_api_keys) == 1
    assert all_api_keys[0].expiry_date <= datetime.utcnow()
    assert all_api_keys[0].secret == api_key.secret
    assert all_api_keys[0].id == api_key.id
    assert all_api_keys[0].service_id == api_key.service_id

    all_history = api_key.get_history_model().query.all()

    assert len(all_history) == 2
    assert all_history[0].id == api_key.id
    assert all_history[1].id == api_key.id
    sorted_all_history = sorted(all_history, key=lambda hist: hist.version)

    # TODO - The versions don't seem to start at 1.  Is this correct?
    assert sorted_all_history[0].version == (sorted_all_history[1].version - 1)


def test_get_api_key_should_raise_exception_when_api_key_does_not_exist(sample_service, fake_uuid):
    with pytest.raises(NoResultFound):
        get_model_api_keys(sample_service().id, id=fake_uuid)


def test_should_return_api_key_for_service(sample_api_key):
    api_key1 = sample_api_key()
    api_key2 = get_model_api_keys(service_id=api_key1.service_id, id=api_key1.id)
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


def test_should_not_allow_duplicate_key_names_per_service(sample_api_key, fake_uuid):
    api_key = sample_api_key()
    api_key = ApiKey(**{
        'id': fake_uuid,
        'service': api_key.service,
        'name': api_key.name,
        'created_by': api_key.created_by,
        'key_type': KEY_TYPE_NORMAL
    })
    with pytest.raises(IntegrityError):
        save_model_api_key(api_key)


def test_save_api_key_can_create_key_with_same_name_if_other_is_expired(notify_db_session, sample_service):
    service = sample_service()
    expired_api_key = ApiKey(**{
        'service': service,
        'name': "normal api key",
        'created_by': service.created_by,
        'key_type': KEY_TYPE_NORMAL,
        'expiry_date': datetime.utcnow(),
    })
    save_model_api_key(expired_api_key)
    api_key = ApiKey(**{
        'service': service,
        'name': "normal api key",
        'created_by': service.created_by,
        'key_type': KEY_TYPE_NORMAL,
    })
    save_model_api_key(api_key)
    keys = ApiKey.query.all()
    api_key_histories = api_key.get_history_model().query.all()

    try:
        assert len(keys) == 2
        assert len(api_key_histories) == 2
    finally:
        # Teardown
        for api_key_history in api_key_histories:
            notify_db_session.session.delete(api_key_history)
        for key in keys:
            notify_db_session.session.delete(key)
        notify_db_session.session.commit()


def test_save_api_key_should_not_create_new_service_history(notify_db_session, sample_service):
    from app.models import Service

    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0

    service = sample_service()
    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    api_key = ApiKey(**{
        'service': service,
        'name': service.name,
        'created_by': service.created_by,
        'key_type': KEY_TYPE_NORMAL
    })
    save_model_api_key(api_key)

    api_key_histories = api_key.get_history_model().query.all()

    try:
        assert Service.query.count() == 1
        assert Service.get_history_model().query.count() == 1
        assert len(api_key_histories) == 1
    finally:
        # Teardown
        for api_key_history in api_key_histories:
            notify_db_session.session.delete(api_key_history)
        notify_db_session.session.delete(api_key)
        notify_db_session.session.commit()


@pytest.mark.parametrize('days_old, expected_length', [(5, 1), (8, 0)])
def test_should_not_return_revoked_api_keys_older_than_7_days(
    notify_db_session, sample_service, days_old, expected_length
):
    service = sample_service()
    expired_api_key = ApiKey(**{
        'service': service,
        'name': service.name,
        'created_by': service.created_by,
        'key_type': KEY_TYPE_NORMAL,
        'expiry_date': datetime.utcnow() - timedelta(days=days_old),
    })
    save_model_api_key(expired_api_key)

    all_api_keys = get_model_api_keys(service_id=service.id)
    api_key_histories = expired_api_key.get_history_model().query.all()

    try:
        assert len(all_api_keys) == expected_length
    finally:
        for api_key_history in api_key_histories:
            notify_db_session.session.delete(api_key_history)
        for api_key in all_api_keys:
            notify_db_session.session.delete(api_key)
        notify_db_session.session.commit()
