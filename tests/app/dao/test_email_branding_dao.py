from uuid import uuid4

import pytest
from sqlalchemy import select

from app.dao.email_branding_dao import (
    dao_get_email_branding_by_id,
    dao_get_email_branding_by_name,
    dao_get_email_branding_options,
    dao_update_email_branding,
)
from app.models import EmailBranding


def test_get_email_branding_options_gets_all_email_branding(sample_email_branding):
    email_branding_1 = sample_email_branding(name=str(uuid4()))
    email_branding_2 = sample_email_branding(name=str(uuid4()))

    email_branding = dao_get_email_branding_options()

    assert len(email_branding) == 2
    assert email_branding_1 == email_branding[0]
    assert email_branding_2 == email_branding[1]


def test_get_email_branding_by_id_gets_correct_email_branding(sample_email_branding):
    email_branding = sample_email_branding(name=str(uuid4()))

    email_branding_from_db = dao_get_email_branding_by_id(email_branding.id)

    assert email_branding_from_db == email_branding


def test_get_email_branding_by_name_gets_correct_email_branding(sample_email_branding):
    email_branding_name = str(uuid4())
    email_branding = sample_email_branding(name=email_branding_name)

    email_branding_from_db = dao_get_email_branding_by_name(email_branding_name)

    assert email_branding_from_db == email_branding


@pytest.mark.serial
def test_update_email_branding(notify_db_session, sample_email_branding):
    updated_name = 'new name'
    sample_email_branding(name=str(uuid4()))

    stmt = select(EmailBranding)
    email_branding = notify_db_session.session.scalars(stmt).all()

    assert len(email_branding) == 1
    assert email_branding[0].name != updated_name

    dao_update_email_branding(email_branding[0], name=updated_name)

    email_branding = notify_db_session.session.scalars(stmt).all()

    assert len(email_branding) == 1
    assert email_branding[0].name == updated_name


@pytest.mark.serial
def test_email_branding_has_no_domain(notify_db_session, sample_email_branding):
    sample_email_branding(name=str(uuid4()))
    stmt = select(EmailBranding)
    email_branding = notify_db_session.session.scalars(stmt).all()
    assert not hasattr(email_branding, 'domain')
