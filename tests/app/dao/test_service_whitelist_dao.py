import uuid

from sqlalchemy import delete, select

from app.models import (
    ServiceWhitelist,
    EMAIL_TYPE,
)
from app.dao.service_whitelist_dao import (
    dao_fetch_service_whitelist,
    dao_add_and_commit_whitelisted_contacts,
    dao_remove_service_whitelist
)


def test_fetch_service_whitelist_gets_whitelists(
    sample_service_whitelist,
):

    service_whitelist = sample_service_whitelist()
    whitelist = dao_fetch_service_whitelist(service_whitelist.service_id)
    assert len(whitelist) == 1
    assert whitelist[0].id == service_whitelist.id


def test_fetch_service_whitelist_ignores_other_service(
    sample_service_whitelist,
):

    sample_service_whitelist()
    assert len(dao_fetch_service_whitelist(uuid.uuid4())) == 0


def test_add_and_commit_whitelisted_contacts_saves_data(
    notify_db_session,
    sample_service,
):

    service = sample_service()
    whitelist = ServiceWhitelist.from_string(service.id, EMAIL_TYPE, 'foo@example.com')

    dao_add_and_commit_whitelisted_contacts([whitelist])

    stmt = select(ServiceWhitelist).where(ServiceWhitelist.service_id == service.id)
    db_contents = notify_db_session.session.scalars(stmt).all()
    assert len(db_contents) == 1
    assert db_contents[0].id == whitelist.id

    # Teardown
    notify_db_session.session.delete(whitelist)
    notify_db_session.session.commit()


def test_remove_service_whitelist_only_removes_for_my_service(
    notify_db_session,
    sample_service,
):

    service_1 = sample_service()
    service_2 = sample_service()
    dao_add_and_commit_whitelisted_contacts([
        ServiceWhitelist.from_string(service_1.id, EMAIL_TYPE, 'service1@example.com'),
        ServiceWhitelist.from_string(service_2.id, EMAIL_TYPE, 'service2@example.com')
    ])

    dao_remove_service_whitelist(service_1.id)

    assert service_1.whitelist == []
    assert len(service_2.whitelist) == 1

    # Teardown
    # service_1 is already marked, just needs to be commit
    notify_db_session.session.execute(delete(ServiceWhitelist).where(ServiceWhitelist.service_id == service_2.id))
    notify_db_session.session.commit()


def test_remove_service_whitelist_does_not_commit(
    notify_db_session,
    sample_service_whitelist,
):

    service_whitelist = sample_service_whitelist()
    dao_remove_service_whitelist(service_whitelist.service_id)

    # since dao_remove_service_whitelist doesn't commit, we can still rollback its changes
    notify_db_session.session.rollback()

    assert notify_db_session.session.get(ServiceWhitelist, service_whitelist.id)

    notify_db_session.session.delete(service_whitelist)
    notify_db_session.session.commit()
