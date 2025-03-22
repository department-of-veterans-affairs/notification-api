import pytest
from sqlalchemy import delete

from app.models import CommunicationItem


@pytest.fixture
def db_session_with_empty_communication_items(notify_db_session):
    stmt = delete(CommunicationItem)
    notify_db_session.session.execute(stmt)
    notify_db_session.session.commit()
    return notify_db_session


class TestGetCommunicationItems:
    # Need test(s) for get_communication_item
    pass
