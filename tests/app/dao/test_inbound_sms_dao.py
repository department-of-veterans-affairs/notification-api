from datetime import datetime
from itertools import product
from uuid import uuid4

from freezegun import freeze_time

from app.constants import EMAIL_TYPE, SMS_TYPE
from app.dao.inbound_sms_dao import (
    dao_get_inbound_sms_for_service,
    dao_count_inbound_sms_for_service,
    delete_inbound_sms_older_than_retention,
    dao_get_inbound_sms_by_id,
    dao_get_paginated_inbound_sms_for_service_for_public_api,
    dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service,
)
from tests.conftest import set_config


def test_get_all_inbound_sms(sample_service, sample_inbound_sms):
    service = sample_service()
    inbound = sample_inbound_sms(service)

    res = dao_get_inbound_sms_for_service(service.id)
    assert len(res) == 1
    assert res[0] == inbound


def test_get_all_inbound_sms_when_none_exist(sample_service):
    res = dao_get_inbound_sms_for_service(sample_service().id)
    assert len(res) == 0


def test_get_all_inbound_sms_limits_and_orders(sample_service, sample_inbound_sms):
    service = sample_service()
    with freeze_time('2017-01-01'):
        sample_inbound_sms(service)
    with freeze_time('2017-01-03'):
        three = sample_inbound_sms(service)
    with freeze_time('2017-01-02'):
        two = sample_inbound_sms(service)

        res = dao_get_inbound_sms_for_service(service.id, limit=2)

    assert len(res) == 2
    assert res[0] == three
    assert res[0].created_at == datetime(2017, 1, 3)
    assert res[1] == two
    assert res[1].created_at == datetime(2017, 1, 2)


def test_get_all_inbound_sms_filters_on_service(sample_service, sample_inbound_sms):
    service_one = sample_service(service_name='one')
    service_two = sample_service(service_name='two')

    sms_one = sample_inbound_sms(service_one)
    sample_inbound_sms(service_two)

    res = dao_get_inbound_sms_for_service(service_one.id)
    assert len(res) == 1
    assert res[0] == sms_one


# This test assumes the local timezone is EST
def test_get_all_inbound_sms_filters_on_time(sample_service, sample_inbound_sms):
    service = sample_service()
    sample_inbound_sms(service, created_at=datetime(2017, 8, 7, 3, 59))  # sunday evening
    sms_two = sample_inbound_sms(service, created_at=datetime(2017, 8, 7, 4, 0))  # monday (7th) morning

    with freeze_time('2017-08-14 12:00'):
        res = dao_get_inbound_sms_for_service(service.id, limit_days=7)

    assert len(res) == 1
    assert res[0] == sms_two


def test_count_inbound_sms_for_service(sample_service, sample_inbound_sms):
    service_one = sample_service()
    service_two = sample_service()

    sample_inbound_sms(service_one)
    sample_inbound_sms(service_one)
    sample_inbound_sms(service_two)

    assert dao_count_inbound_sms_for_service(service_one.id, limit_days=1) == 2


# This test assumes the local timezone is EST
def test_count_inbound_sms_for_service_filters_messages_older_than_n_days(sample_service, sample_inbound_sms):
    service = sample_service()
    # test between evening sunday 2nd of june and morning of monday 3rd
    sample_inbound_sms(service, created_at=datetime(2019, 6, 3, 3, 59))
    sample_inbound_sms(service, created_at=datetime(2019, 6, 3, 3, 59))
    sample_inbound_sms(service, created_at=datetime(2019, 6, 3, 4, 1))

    with freeze_time('Monday 10th June 2019 12:00'):
        assert dao_count_inbound_sms_for_service(service.id, limit_days=7) == 1


@freeze_time('1998-06-08 12:00:00')
# This test assumes the local timezone is EST
def test_should_delete_inbound_sms_according_to_data_retention(
    sample_service,
    sample_inbound_sms,
    sample_service_data_retention,
):
    no_retention_service = sample_service(service_name=f'no retention {uuid4()}')
    short_retention_service = sample_service(service_name=f'three days {uuid4()}')
    long_retention_service = sample_service(service_name=f'thirty days {uuid4()}')

    services = [short_retention_service, no_retention_service, long_retention_service]

    sample_service_data_retention(long_retention_service, notification_type=SMS_TYPE, days_of_retention=30)
    sample_service_data_retention(short_retention_service, notification_type=SMS_TYPE, days_of_retention=3)
    # email retention doesn't affect anything
    sample_service_data_retention(short_retention_service, notification_type=EMAIL_TYPE, days_of_retention=4)

    dates = [
        datetime(1998, 6, 5, 4, 00),  # just before three days
        datetime(1998, 6, 5, 3, 59),  # older than three days
        datetime(1998, 6, 1, 4, 00),  # just before seven days
        datetime(1998, 6, 1, 3, 59),  # older than seven days
        datetime(1998, 5, 1, 0, 0),  # older than thirty days
    ]

    for date, service in product(dates, services):
        sample_inbound_sms(service, created_at=date)

    deleted_count = delete_inbound_sms_older_than_retention()

    # four deleted for the 3-day service, two for the default seven days one, one for the 30 day
    assert deleted_count == 7
    assert {x.created_at for x in dao_get_inbound_sms_for_service(short_retention_service.id)} == set(dates[:1])
    assert {x.created_at for x in dao_get_inbound_sms_for_service(no_retention_service.id)} == set(dates[:3])
    assert {x.created_at for x in dao_get_inbound_sms_for_service(long_retention_service.id)} == set(dates[:4])


def test_get_inbound_sms_by_id_returns(sample_service, sample_inbound_sms):
    service = sample_service()
    inbound_sms = sample_inbound_sms(service=service)
    inbound_from_db = dao_get_inbound_sms_by_id(inbound_sms.service.id, inbound_sms.id)

    assert inbound_sms == inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service_for_public_api(sample_service, sample_inbound_sms):
    service = sample_service()
    inbound_sms = sample_inbound_sms(service=service)
    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(inbound_sms.service.id)

    assert inbound_sms == inbound_from_db[0]


def test_dao_get_paginated_inbound_sms_for_service_for_public_api_return_only_for_service(
    sample_service,
    sample_inbound_sms,
):
    service = sample_service()
    inbound_sms = sample_inbound_sms(service=service)
    another_service = sample_service(service_name='another service')
    another_inbound_sms = sample_inbound_sms(another_service)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(inbound_sms.service.id)

    assert inbound_sms in inbound_from_db
    assert another_inbound_sms not in inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service_for_public_api_no_inbound_sms_returns_empty_list(sample_service):
    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(sample_service().id)

    assert inbound_from_db == []


def test_dao_get_paginated_inbound_sms_for_service_for_public_api_page_size_returns_correct_size(
    sample_service,
    sample_inbound_sms,
):
    service = sample_service()
    inbound_sms_list = [
        sample_inbound_sms(service),
        sample_inbound_sms(service),
        sample_inbound_sms(service),
        sample_inbound_sms(service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(
        service.id, older_than=reversed_inbound_sms[1].id, page_size=2
    )

    assert len(inbound_from_db) == 2


def test_dao_get_paginated_inbound_sms_for_service_for_public_api_older_than_returns_correct_list(
    sample_service, sample_inbound_sms
):
    service = sample_service()
    inbound_sms_list = [
        sample_inbound_sms(service),
        sample_inbound_sms(service),
        sample_inbound_sms(service),
        sample_inbound_sms(service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(
        service.id, older_than=reversed_inbound_sms[1].id, page_size=2
    )

    expected_inbound_sms = reversed_inbound_sms[2:]

    assert expected_inbound_sms == inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service_for_public_api_older_than_end_returns_empty_list(
    sample_service,
    sample_inbound_sms,
):
    service = sample_service()
    inbound_sms_list = [
        sample_inbound_sms(service),
        sample_inbound_sms(service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service_for_public_api(
        service.id, older_than=reversed_inbound_sms[1].id, page_size=2
    )

    assert inbound_from_db == []


def test_most_recent_inbound_sms_only_returns_most_recent_for_each_number(
    notify_api,
    sample_service,
    sample_inbound_sms,
):
    service = sample_service()
    sample_inbound_sms(service, user_number='447700900111', content='111 1', created_at=datetime(2017, 1, 1))
    sample_inbound_sms(service, user_number='447700900111', content='111 2', created_at=datetime(2017, 1, 2))
    sample_inbound_sms(service, user_number='447700900111', content='111 3', created_at=datetime(2017, 1, 3))
    sample_inbound_sms(service, user_number='447700900111', content='111 4', created_at=datetime(2017, 1, 4))
    sample_inbound_sms(service, user_number='447700900111', content='111 5', created_at=datetime(2017, 1, 5))
    sample_inbound_sms(service, user_number='447700900222', content='222 1', created_at=datetime(2017, 1, 1))
    sample_inbound_sms(service, user_number='447700900222', content='222 2', created_at=datetime(2017, 1, 2))

    with set_config(notify_api, 'PAGE_SIZE', 3):
        with freeze_time('2017-01-02'):
            res = dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(service.id, limit_days=7, page=1)  # noqa

    assert len(res.items) == 2
    assert res.has_next is False
    assert res.per_page == 3
    assert res.items[0].content == '111 5'
    assert res.items[1].content == '222 2'


def test_most_recent_inbound_sms_paginates_properly(notify_api, sample_service, sample_inbound_sms):
    service = sample_service()
    sample_inbound_sms(service, user_number='447700900111', content='111 1', created_at=datetime(2017, 1, 1))
    sample_inbound_sms(service, user_number='447700900111', content='111 2', created_at=datetime(2017, 1, 2))
    sample_inbound_sms(service, user_number='447700900222', content='222 1', created_at=datetime(2017, 1, 3))
    sample_inbound_sms(service, user_number='447700900222', content='222 2', created_at=datetime(2017, 1, 4))
    sample_inbound_sms(service, user_number='447700900333', content='333 1', created_at=datetime(2017, 1, 5))
    sample_inbound_sms(service, user_number='447700900333', content='333 2', created_at=datetime(2017, 1, 6))
    sample_inbound_sms(service, user_number='447700900444', content='444 1', created_at=datetime(2017, 1, 7))
    sample_inbound_sms(service, user_number='447700900444', content='444 2', created_at=datetime(2017, 1, 8))

    with set_config(notify_api, 'PAGE_SIZE', 2):
        with freeze_time('2017-01-02'):
            # first page has most recent 444 and 333
            res = dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(service.id, limit_days=7, page=1)  # noqa
            assert len(res.items) == 2
            assert res.has_next is True
            assert res.per_page == 2
            assert res.items[0].content == '444 2'
            assert res.items[1].content == '333 2'

            # second page has no 444 or 333 - just most recent 222 and 111
            res = dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(service.id, limit_days=7, page=2)  # noqa
            assert len(res.items) == 2
            assert res.has_next is False
            assert res.items[0].content == '222 2'
            assert res.items[1].content == '111 2'


# This test assumes the local timezone is EST
def test_most_recent_inbound_sms_only_returns_values_within_7_days(sample_service, sample_inbound_sms):
    service = sample_service()
    # just out of bounds
    sample_inbound_sms(service, user_number='1', content='old', created_at=datetime(2017, 4, 3, 3, 59, 59))
    # just in bounds
    sample_inbound_sms(service, user_number='2', content='new', created_at=datetime(2017, 4, 3, 4, 0, 0))

    with freeze_time('Monday 10th April 2017 12:00:00'):
        res = dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(service.id, limit_days=7, page=1)  # noqa

    assert len(res.items) == 1
    assert res.items[0].content == 'new'
