import uuid
from datetime import datetime

import pytest
from freezegun import freeze_time
from sqlalchemy import select

from app import db
from app.models import Service
from app.dao.services_dao import dao_archive_service
from app.dao.api_key_dao import expire_api_key
from app.dao.templates_dao import dao_update_template

from tests import create_authorization_header, unwrap_function
from tests.app.db import create_template, create_api_key


def test_archive_only_allows_post(client):
    auth_header = create_authorization_header()
    response = client.get('/service/{}/archive'.format(uuid.uuid4()), headers=[auth_header])
    assert response.status_code == 405


def test_archive_service_errors_with_bad_service_id(client):
    auth_header = create_authorization_header()
    response = client.post('/service/{}/archive'.format(uuid.uuid4()), headers=[auth_header])
    assert response.status_code == 404


def test_deactivating_inactive_service_does_nothing(client, notify_db_session, sample_service):
    service = sample_service()
    dao_archive_service(service.id)
    auth_header = create_authorization_header()
    
    response = client.post('/service/{}/archive'.format(service.id), headers=[auth_header])
    assert response.status_code == 204
    assert service.name == service.name
    stmt = select(Service).where(Service.id == service.id)
    assert notify_db_session.session.scalar(stmt).name.startswith('_archived_')


@pytest.fixture
@freeze_time('2018-04-21 14:00')
def archived_service(client, sample_service, sample_template, sample_api_key):
    service = sample_service(email_from='sample.service')
    sample_template(service=service, name=f'arch_service_template {uuid.uuid4()}')
    sample_template(service=service, name=f'arch_service_template {uuid.uuid4()}')
    sample_api_key(service=service)
    sample_api_key(service=service)

    auth_header = create_authorization_header()
    response = client.post('/service/{}/archive'.format(service.id), headers=[auth_header])

    assert response.status_code == 204
    assert response.data == b''
    return service


def test_deactivating_service_changes_name_and_email(archived_service):
    assert archived_service.name.startswith('_archived_2018-04-21_14:00:00_')
    assert archived_service.email_from == '_archived_2018-04-21_14:00:00_sample.service'


def test_deactivating_service_revokes_api_keys(archived_service):
    assert len(archived_service.api_keys) == 2
    for key in archived_service.api_keys:
        assert key.expiry_date is not None
        assert key.version == 2


def test_deactivating_service_archives_templates(archived_service):
    assert len(archived_service.templates) == 2
    for template in archived_service.templates:
        assert template.archived is True
        assert template.version == 2


def test_deactivating_service_creates_history(archived_service):
    ServiceHistory = Service.get_history_model()
    history = ServiceHistory.query.filter_by(
        id=archived_service.id
    ).order_by(
        ServiceHistory.version.desc()
    ).first()

    assert history.version == 2
    assert history.active is False


@pytest.fixture
def archived_service_with_deleted_stuff(client, sample_api_key, sample_service, sample_template):
    with freeze_time('2001-01-01'):
        service = sample_service()
        template = sample_template(service=service, name=f'arch_service_template {uuid.uuid4()}')
        api_key = sample_api_key(service=service)

        expire_api_key(service.id, api_key.id)

        template.archived = True
        dao_update_template(template)

    with freeze_time('2002-02-02'):
        auth_header = create_authorization_header()
        response = client.post('/service/{}/archive'.format(service.id), headers=[auth_header])

    assert response.status_code == 204
    assert response.data == b''
    return service


def test_deactivating_service_doesnt_affect_existing_archived_templates(archived_service_with_deleted_stuff):
    assert archived_service_with_deleted_stuff.templates[0].archived is True
    assert archived_service_with_deleted_stuff.templates[0].updated_at == datetime(2001, 1, 1, 0, 0, 0)
    assert archived_service_with_deleted_stuff.templates[0].version == 2


def test_deactivating_service_doesnt_affect_existing_revoked_api_keys(archived_service_with_deleted_stuff):
    assert archived_service_with_deleted_stuff.api_keys[0].expiry_date == datetime(2001, 1, 1, 0, 0, 0)
    assert archived_service_with_deleted_stuff.api_keys[0].version == 2


def test_deactivating_service_rolls_back_everything_on_error(sample_service, sample_api_key, sample_template):
    service = sample_service()
    template = sample_template(service=service)
    api_key = sample_api_key(service=service)
    unwrapped_deactive_service = unwrap_function(dao_archive_service)

    unwrapped_deactive_service(service.id)

    assert service in db.session.dirty
    assert api_key in db.session.dirty
    assert template in db.session.dirty
