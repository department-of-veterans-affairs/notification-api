import pytest

from app.dao.active_user_emails_dao import (
    get_active_business_contact_emails,
    get_active_technical_contact_emails,
    get_all_active_user_emails,
)
from app.models import UserServiceRoles
from sqlalchemy import delete


def _add_user_service_role(notify_db_session, user_id, service_id, role):
    user_service_role = UserServiceRoles(
        user_id=user_id,
        service_id=service_id,
        role=role,
    )
    notify_db_session.session.add(user_service_role)
    notify_db_session.session.commit()
    return user_service_role


def _cleanup_user_service_roles(notify_db_session, role_ids):
    stmt = delete(UserServiceRoles).where(UserServiceRoles.id.in_(role_ids))
    notify_db_session.session.execute(stmt)
    notify_db_session.session.commit()


@pytest.mark.serial
def test_get_active_business_contact_emails_returns_active_business_contacts_only(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()

    active_business_user = sample_user(email='business-contact@va.gov')
    active_technical_user = sample_user(email='technical-contact@va.gov')
    inactive_business_user = sample_user(email='inactive-business@va.gov', state='inactive')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_business_user.id, service.id, 'business_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, active_technical_user.id, service.id, 'technical_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, inactive_business_user.id, service.id, 'business_contact').id
    )

    try:
        emails = get_active_business_contact_emails()
        assert set(emails) == {'business-contact@va.gov'}
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_technical_contact_emails_returns_active_technical_contacts_only(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()

    active_business_user = sample_user(email='business-contact-2@va.gov')
    active_technical_user = sample_user(email='technical-contact-2@va.gov')
    inactive_technical_user = sample_user(email='inactive-technical@va.gov', state='inactive')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_business_user.id, service.id, 'business_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, active_technical_user.id, service.id, 'technical_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, inactive_technical_user.id, service.id, 'technical_contact').id
    )

    try:
        emails = get_active_technical_contact_emails()
        assert set(emails) == {'technical-contact-2@va.gov'}
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_all_active_user_emails_returns_all_active_users(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()

    active_business_user = sample_user(email='all-active-business@va.gov')
    sample_user(email='all-active-no-role@va.gov')
    sample_user(email='all-active-inactive@va.gov', state='inactive')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_business_user.id, service.id, 'business_contact').id
    )

    try:
        emails = get_all_active_user_emails()
        assert 'all-active-business@va.gov' in emails
        assert 'all-active-no-role@va.gov' in emails
        assert 'all-active-inactive@va.gov' not in emails
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_business_contact_emails_returns_empty_when_no_business_contacts(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()
    active_technical_user = sample_user(email='no-business-tech@va.gov')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_technical_user.id, service.id, 'technical_contact').id
    )

    try:
        emails = get_active_business_contact_emails()
        assert emails == []
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_technical_contact_emails_returns_empty_when_no_technical_contacts(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()
    active_business_user = sample_user(email='no-technical-business@va.gov')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_business_user.id, service.id, 'business_contact').id
    )

    try:
        emails = get_active_technical_contact_emails()
        assert emails == []
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_all_active_user_emails_returns_empty_when_no_active_users(
    sample_user,
):
    sample_user(email='inactive-only-1@va.gov', state='inactive')
    sample_user(email='inactive-only-2@va.gov', state='pending')

    emails = get_all_active_user_emails()

    assert emails == []


@pytest.mark.serial
def test_get_active_business_contact_emails_deduplicates_multiple_role_rows_for_same_user(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    user = sample_user(email='duplicate-business@va.gov')
    service_1 = sample_service(user=user)
    service_2 = sample_service(user=user)

    role_ids.append(_add_user_service_role(notify_db_session, user.id, service_1.id, 'business_contact').id)
    role_ids.append(_add_user_service_role(notify_db_session, user.id, service_2.id, 'business_contact').id)

    try:
        emails = get_active_business_contact_emails()
        assert emails.count('duplicate-business@va.gov') == 1
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_technical_contact_emails_deduplicates_multiple_role_rows_for_same_user(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    user = sample_user(email='duplicate-technical@va.gov')
    service_1 = sample_service(user=user)
    service_2 = sample_service(user=user)

    role_ids.append(_add_user_service_role(notify_db_session, user.id, service_1.id, 'technical_contact').id)
    role_ids.append(_add_user_service_role(notify_db_session, user.id, service_2.id, 'technical_contact').id)

    try:
        emails = get_active_technical_contact_emails()
        assert emails.count('duplicate-technical@va.gov') == 1
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_email_values_are_returned_as_is_for_invalid_email_strings(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()
    invalid_email_user = sample_user(email='not-an-email', state='active')

    role_ids.append(_add_user_service_role(notify_db_session, invalid_email_user.id, service.id, 'business_contact').id)

    try:
        business_emails = get_active_business_contact_emails()
        all_active_emails = get_all_active_user_emails()

        assert 'not-an-email' in business_emails
        assert 'not-an-email' in all_active_emails
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)
