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


@pytest.mark.serial
def test_get_active_business_contact_emails_lowercases_and_deduplicates_mixed_case_addresses(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()
    lower_user = sample_user(email='john@va.gov')
    mixed_user = sample_user(email='John@VA.gov')

    role_ids.append(_add_user_service_role(notify_db_session, lower_user.id, service.id, 'business_contact').id)
    role_ids.append(_add_user_service_role(notify_db_session, mixed_user.id, service.id, 'business_contact').id)

    try:
        emails = get_active_business_contact_emails()
        assert emails == ['john@va.gov']
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_technical_contact_emails_lowercases_and_deduplicates_mixed_case_addresses(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()
    upper_user = sample_user(email='JANE@VA.GOV')
    mixed_user = sample_user(email='Jane@va.gov')

    role_ids.append(_add_user_service_role(notify_db_session, upper_user.id, service.id, 'technical_contact').id)
    role_ids.append(_add_user_service_role(notify_db_session, mixed_user.id, service.id, 'technical_contact').id)

    try:
        emails = get_active_technical_contact_emails()
        assert emails == ['jane@va.gov']
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_all_active_user_emails_lowercases_and_deduplicates_mixed_case_addresses(
    sample_user,
):
    sample_user(email='ALICE@VA.GOV', state='active')
    sample_user(email='Alice@va.gov', state='active')

    emails = get_all_active_user_emails()

    assert emails.count('alice@va.gov') == 1


@pytest.mark.serial
def test_user_email_appears_in_role_specific_and_all_active_lists(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    user = sample_user(email='unique@va.gov', state='active')
    service = sample_service()

    role_ids.append(_add_user_service_role(notify_db_session, user.id, service.id, 'business_contact').id)

    try:
        business_emails = get_active_business_contact_emails()
        all_active_emails = get_all_active_user_emails()

        assert 'unique@va.gov' in business_emails
        assert 'unique@va.gov' in all_active_emails
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)


@pytest.mark.serial
def test_get_active_user_email_queries_exclude_archived_prefixed_emails(
    notify_db_session,
    sample_service,
    sample_user,
):
    role_ids = []
    service = sample_service()

    active_business_user = sample_user(email='business-ok@va.gov', state='active')
    active_technical_user = sample_user(email='technical-ok@va.gov', state='active')
    archived_business_user = sample_user(email='_archived-business@va.gov', state='active')
    archived_technical_user = sample_user(email='_ARCHIVED-technical@va.gov', state='active')

    role_ids.append(
        _add_user_service_role(notify_db_session, active_business_user.id, service.id, 'business_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, active_technical_user.id, service.id, 'technical_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, archived_business_user.id, service.id, 'business_contact').id
    )
    role_ids.append(
        _add_user_service_role(notify_db_session, archived_technical_user.id, service.id, 'technical_contact').id
    )

    try:
        business_emails = get_active_business_contact_emails()
        technical_emails = get_active_technical_contact_emails()
        all_active_emails = get_all_active_user_emails()

        assert 'business-ok@va.gov' in business_emails
        assert '_archived-business@va.gov' not in business_emails

        assert 'technical-ok@va.gov' in technical_emails
        assert '_archived-technical@va.gov' not in technical_emails

        assert 'business-ok@va.gov' in all_active_emails
        assert 'technical-ok@va.gov' in all_active_emails
        assert '_archived-business@va.gov' not in all_active_emails
        assert '_archived-technical@va.gov' not in all_active_emails
        assert '_archived-all@va.gov' not in all_active_emails
    finally:
        _cleanup_user_service_roles(notify_db_session, role_ids)
