from datetime import datetime
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dao.service_data_retention_dao import (
    fetch_service_data_retention,
    insert_service_data_retention,
    fetch_service_data_retention_by_id,
    fetch_service_data_retention_by_notification_type,
)
from app.models import ServiceDataRetention
from tests.app.db import create_service_data_retention


def test_fetch_service_data_retention(sample_service):
    service = sample_service()
    email_data_retention = insert_service_data_retention(service.id, 'email', 3)
    letter_data_retention = insert_service_data_retention(service.id, 'letter', 30)
    sms_data_retention = insert_service_data_retention(service.id, 'sms', 5)

    list_of_data_retention = fetch_service_data_retention(service.id)

    assert len(list_of_data_retention) == 3
    assert list_of_data_retention[0] == email_data_retention
    assert list_of_data_retention[1] == sms_data_retention
    assert list_of_data_retention[2] == letter_data_retention


def test_fetch_service_data_retention_only_returns_row_for_service(sample_service):
    service = sample_service()
    another_service = sample_service()
    email_data_retention = insert_service_data_retention(service.id, 'email', 3)
    letter_data_retention = insert_service_data_retention(service.id, 'letter', 30)
    insert_service_data_retention(another_service.id, 'sms', 5)

    list_of_data_retention = fetch_service_data_retention(service.id)
    assert len(list_of_data_retention) == 2
    assert list_of_data_retention[0] == email_data_retention
    assert list_of_data_retention[1] == letter_data_retention


def test_fetch_service_data_retention_returns_empty_list_when_no_rows_for_service(sample_service):
    empty_list = fetch_service_data_retention(sample_service().id)
    assert not empty_list


def test_fetch_service_data_retention_by_id(sample_service):
    service = sample_service()
    email_data_retention = insert_service_data_retention(service.id, 'email', 3)
    insert_service_data_retention(service.id, 'sms', 13)
    result = fetch_service_data_retention_by_id(service.id, email_data_retention.id)
    assert result == email_data_retention


def test_fetch_service_data_retention_by_id_returns_none_if_not_found(sample_service):
    result = fetch_service_data_retention_by_id(sample_service().id, uuid.uuid4())
    assert not result


def test_fetch_service_data_retention_by_id_returns_none_if_id_not_for_service(sample_service):
    another_service = sample_service()
    email_data_retention = insert_service_data_retention(sample_service().id, 'email', 3)
    result = fetch_service_data_retention_by_id(another_service.id, email_data_retention.id)
    assert not result


def test_insert_service_data_retention(
    notify_db_session,
    sample_service,
):
    service = sample_service()
    insert_service_data_retention(service_id=service.id, notification_type='email', days_of_retention=3)

    stmt = select(ServiceDataRetention).where(ServiceDataRetention.service_id == service.id)
    results = notify_db_session.session.scalars(stmt).all()

    assert len(results) == 1
    assert results[0].service_id == service.id
    assert results[0].notification_type == 'email'
    assert results[0].days_of_retention == 3
    assert results[0].created_at.date() == datetime.utcnow().date()


def test_insert_service_data_retention_throws_unique_constraint(sample_service):
    service = sample_service()
    insert_service_data_retention(service_id=service.id, notification_type='email', days_of_retention=3)
    with pytest.raises(expected_exception=IntegrityError):
        insert_service_data_retention(service_id=service.id, notification_type='email', days_of_retention=5)


@pytest.mark.parametrize(
    'notification_type, alternate', [('sms', 'email'), ('email', 'sms'), ('letter', 'email'), ('letter', 'sms')]
)
def test_fetch_service_data_retention_by_notification_type(sample_service, notification_type, alternate):
    service = sample_service()
    data_retention = create_service_data_retention(service=service, notification_type=notification_type)
    create_service_data_retention(service=service, notification_type=alternate)
    result = fetch_service_data_retention_by_notification_type(service.id, notification_type)
    assert result == data_retention


def test_fetch_service_data_retention_by_notification_type_returns_none_when_no_rows(sample_service):
    assert not fetch_service_data_retention_by_notification_type(sample_service().id, 'email')
