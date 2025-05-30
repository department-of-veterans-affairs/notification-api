from calendar import monthrange
from datetime import datetime, timedelta, date
from decimal import Decimal

from freezegun import freeze_time
from notifications_utils.timezones import convert_utc_to_local_timezone
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine.row import Row

from app import db
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
)
from app.dao.fact_billing_dao import (
    delete_billing_data_for_service_for_day,
    fetch_billing_data_for_day,
    fetch_billing_totals_for_year,
    fetch_monthly_billing_for_year,
    fetch_sms_free_allowance_remainder,
    fetch_nightly_billing_counts,
    get_rate,
    get_rates_for_billing,
)
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.models import FactBilling


ORG_NAME = 'Org for {}'


# This take a long time to execute.  Can it be replaced with a bulk insert?
def set_up_yearly_data(sample_service, sample_template, sample_ft_billing, years):
    service = sample_service()
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    letter_template = sample_template(service=service, template_type=LETTER_TYPE)
    for year in years:
        for month in range(1, 13):
            mon = str(month).zfill(2)
            for day in range(1, monthrange(year, month)[1] + 1):
                d = str(day).zfill(2)
                sample_ft_billing(
                    utc_date='{}-{}-{}'.format(year, mon, d),
                    service=service,
                    template=sms_template,
                    notification_type=SMS_TYPE,
                    rate=0.162,
                )
                sample_ft_billing(
                    utc_date='{}-{}-{}'.format(year, mon, d),
                    service=service,
                    template=email_template,
                    notification_type=EMAIL_TYPE,
                    rate=0,
                )
                sample_ft_billing(
                    utc_date='{}-{}-{}'.format(year, mon, d),
                    service=service,
                    template=letter_template,
                    notification_type=LETTER_TYPE,
                    rate=0.33,
                    postage='second',
                )
                sample_ft_billing(
                    utc_date='{}-{}-{}'.format(year, mon, d),
                    service=service,
                    template=letter_template,
                    notification_type=LETTER_TYPE,
                    rate=0.30,
                    postage='second',
                )
    return service


def test_fetch_billing_data_for_today_includes_data_with_the_right_status(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    # these statuses need to be ones that are not in NOTIFICATION_STATUS_TYPES_BILLABLE
    sample_notification(template=template, status=NOTIFICATION_CREATED)
    sample_notification(template=template, status=NOTIFICATION_PENDING)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert isinstance(results, list) and not results, 'Should be an empty list'

    for status in (NOTIFICATION_DELIVERED, NOTIFICATION_SENDING, NOTIFICATION_TEMPORARY_FAILURE):
        sample_notification(template=template, status=status)

    results = fetch_billing_data_for_day(today, service.id)

    assert len(results) == 1
    assert results[0].notifications_sent == 3


def test_fetch_billing_data_for_today_includes_data_with_the_right_key_type(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)

    for key_type in (KEY_TYPE_NORMAL, KEY_TYPE_TEST, KEY_TYPE_TEAM):
        sample_notification(template=template, status=NOTIFICATION_DELIVERED, key_type=key_type)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


@freeze_time('2018-04-02 06:20:00')
# This test assumes the local timezone is EST
def test_fetch_billing_data_for_today_includes_data_with_the_right_date(
    sample_service,
    sample_template,
    sample_notification,
):
    process_day = datetime(2018, 4, 1, 13, 30, 0)
    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, created_at=process_day)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, created_at=datetime(2018, 4, 1, 4, 23, 23))

    sample_notification(template=template, status=NOTIFICATION_DELIVERED, created_at=datetime(2018, 3, 31, 20, 23, 23))
    sample_notification(template=template, status=NOTIFICATION_SENDING, created_at=process_day + timedelta(days=1))

    day_under_test = convert_utc_to_local_timezone(process_day)
    results = fetch_billing_data_for_day(day_under_test, service.id)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


@freeze_time('2018-04-02 06:20:00')
def test_fetch_nightly_billing_counts_retrieves_correct_data_within_process_day(
    sample_service,
    sample_template,
    sample_notification,
):
    """
    This test assumes the local timezone is EST.
    """

    process_day = datetime(2018, 4, 1, 13, 30, 0)
    service = sample_service()
    template1 = sample_template(service=service)
    template2 = sample_template(service=service)

    # Create 3 SMS notifications for the given process date.
    sample_notification(
        template=template2,
        status=NOTIFICATION_DELIVERED,
        created_at=process_day,
        billing_code='test_code',
        sms_sender_id=service.service_sms_senders[0].id,
        segments_count=3,
        cost_in_millicents=1234.5,
    )
    sample_notification(
        template=template1,
        status=NOTIFICATION_DELIVERED,
        created_at=process_day,
        sms_sender_id=service.service_sms_senders[0].id,
        segments_count=5,
        cost_in_millicents=55.5,
    )
    sample_notification(
        template=template1,
        status=NOTIFICATION_DELIVERED,
        created_at=datetime(2018, 4, 1, 4, 23, 23),
        sms_sender_id=service.service_sms_senders[0].id,
        segments_count=4,
        cost_in_millicents=44.4,
    )

    # Create 2 SMS notifications not for the given process date.
    sample_notification(
        template=template1,
        status=NOTIFICATION_DELIVERED,
        created_at=datetime(2018, 3, 31, 20, 23, 23),
        sms_sender_id=service.service_sms_senders[0].id,
        segments_count=1,
        cost_in_millicents=0.0005,
    )
    sample_notification(
        template=template1,
        status=NOTIFICATION_SENDING,
        created_at=process_day + timedelta(days=1),
        sms_sender_id=service.service_sms_senders[0].id,
        segments_count=1,
        cost_in_millicents=0.0005,
    )

    day_under_test = convert_utc_to_local_timezone(process_day)
    results = fetch_nightly_billing_counts(day_under_test)

    assert len(results) == 2
    assert isinstance(results[0], Row), 'fetch_nightly_billing_counts should return a cursor to SQLAchemy Row instances'
    results.sort(key=lambda x: x.count, reverse=True)
    assert results[0].count == 2
    assert results[0].total_message_parts == 9
    assert results[0].total_cost == 99.9

    assert results[0].service_name == service.name
    assert results[0].sender == service.service_sms_senders[0].sms_sender
    assert results[0].sender_id == service.service_sms_senders[0].id

    assert results[1].billing_code == 'test_code'
    assert results[1].template_name.startswith('function template')
    assert results[1].sender == service.service_sms_senders[0].sms_sender
    assert results[1].sender_id == service.service_sms_senders[0].id


def test_fetch_billing_data_for_day_is_grouped_by_template_and_notification_type(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_service(
    sample_service,
    sample_template,
    sample_notification,
):
    service_1 = sample_service()
    email_template = sample_template(service=service_1)
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)

    service_2 = sample_service()
    sms_template = sample_template(service=service_2)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, (service_1.id, service_2.id))
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


@pytest.mark.serial
def test_fetch_billing_data_for_day_is_grouped_by_provider(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    template = sample_template(service=service)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, sent_by='mmg')
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, sent_by='firetext')

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)

    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


@pytest.mark.serial
def test_fetch_billing_data_for_day_is_grouped_by_rate_mulitplier(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    template = sample_template(service=service)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, rate_multiplier=1)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, rate_multiplier=2)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


@pytest.mark.serial
def test_fetch_billing_data_for_day_is_grouped_by_international(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    template = sample_template(service=service)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, international=True)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED, international=False)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_notification_type(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    letter_template = sample_template(service=service, template_type=LETTER_TYPE)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=letter_template, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 3
    notification_types = [x[2] for x in results if x[2] in [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]]
    assert len(notification_types) == 3


def test_fetch_billing_data_for_day_groups_by_postage(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    letter_template = sample_template(service=service, template_type=LETTER_TYPE)
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    sample_notification(template=letter_template, status=NOTIFICATION_DELIVERED, postage='first')
    sample_notification(template=letter_template, status=NOTIFICATION_DELIVERED, postage='first')
    sample_notification(template=letter_template, status=NOTIFICATION_DELIVERED, postage='second')
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 3


def test_fetch_billing_data_for_day_sets_postage_for_emails_and_sms_to_none(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    sample_notification(template=sms_template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=email_template, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 2
    assert results[0].postage == 'none'
    assert results[1].postage == 'none'


def test_fetch_billing_data_for_day_returns_empty_list(sample_service):
    service = sample_service()
    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert results == []


@freeze_time('1990-08-16')
def test_fetch_billing_data_for_day_uses_notification_history(
    sample_service,
    sample_template,
    sample_notification_history,
):
    service = sample_service()
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    sample_notification_history(
        template=sms_template, status=NOTIFICATION_DELIVERED, created_at=datetime.utcnow() - timedelta(days=8)
    )
    sample_notification_history(
        template=sms_template, status=NOTIFICATION_DELIVERED, created_at=datetime.utcnow() - timedelta(days=8)
    )

    results = fetch_billing_data_for_day(
        convert_utc_to_local_timezone(datetime.utcnow()) - timedelta(days=8), service.id
    )
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_returns_list_for_given_service(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    service_2 = sample_service()
    template = sample_template(service=service)
    template_2 = sample_template(service=service_2)
    sample_notification(template=template, status=NOTIFICATION_DELIVERED)
    sample_notification(template=template_2, status=NOTIFICATION_DELIVERED)

    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)
    assert len(results) == 1
    assert results[0].service_id == service.id


def test_fetch_billing_data_for_day_bills_correctly_for_status(
    sample_service,
    sample_template,
    sample_notification,
):
    service = sample_service()
    sms_template = sample_template(service=service, template_type=SMS_TYPE)
    email_template = sample_template(service=service, template_type=EMAIL_TYPE)
    letter_template = sample_template(service=service, template_type=LETTER_TYPE)
    for status in NOTIFICATION_STATUS_TYPES:
        sample_notification(template=sms_template, status=status)
        sample_notification(template=email_template, status=status)
        sample_notification(template=letter_template, status=status)
    today = convert_utc_to_local_timezone(datetime.utcnow())
    results = fetch_billing_data_for_day(today, service.id)

    sms_results = [x for x in results if x[2] == SMS_TYPE]
    email_results = [x for x in results if x[2] == EMAIL_TYPE]
    letter_results = [x for x in results if x[2] == LETTER_TYPE]
    assert 7 == sms_results[0][7]
    assert 7 == email_results[0][7]
    assert 3 == letter_results[0][7]


def test_get_rates_for_billing(sample_rate, sample_letter_rate):
    sample_rate(start_date=datetime.utcnow(), value=12, notification_type=EMAIL_TYPE)
    sample_rate(start_date=datetime.utcnow(), value=22, notification_type=SMS_TYPE)
    sample_rate(start_date=datetime.utcnow(), value=33, notification_type=EMAIL_TYPE)
    sample_letter_rate(start_date=datetime.utcnow(), rate=0.66, post_class='first')
    sample_letter_rate(start_date=datetime.utcnow(), rate=0.33, post_class='second')
    non_letter_rates, letter_rates = get_rates_for_billing()

    assert len(non_letter_rates) == 3
    assert len(letter_rates) == 2


@freeze_time('2017-06-01 12:00')
def test_get_rate(sample_rate, sample_letter_rate):
    sample_rate(start_date=datetime(2017, 5, 30, 23, 0), value=1.2, notification_type=EMAIL_TYPE)
    sample_rate(start_date=datetime(2017, 5, 30, 23, 0), value=2.2, notification_type=SMS_TYPE)
    sample_rate(start_date=datetime(2017, 5, 30, 23, 0), value=3.3, notification_type=EMAIL_TYPE)
    sample_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.66, post_class='first')
    sample_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.3, post_class='second')

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(
        non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type=SMS_TYPE, date=date(2017, 6, 1)
    )
    letter_rate = get_rate(
        non_letter_rates=non_letter_rates,
        letter_rates=letter_rates,
        notification_type=LETTER_TYPE,
        crown=True,
        letter_page_count=1,
        date=date(2017, 6, 1),
    )

    assert rate == 2.2
    assert letter_rate == Decimal('0.3')


@pytest.mark.parametrize('letter_post_class,expected_rate', [('first', '0.61'), ('second', '0.35')])
def test_get_rate_filters_letters_by_post_class(letter_post_class, expected_rate, sample_letter_rate):
    sample_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.61, post_class='first')
    sample_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.35, post_class='second')

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, LETTER_TYPE, datetime(2018, 10, 1), True, 2, letter_post_class)
    assert rate == Decimal(expected_rate)


def test_get_rate_for_letters_when_page_count_is_zero(notify_api):
    non_letter_rates, letter_rates = get_rates_for_billing()
    letter_rate = get_rate(
        non_letter_rates=non_letter_rates,
        letter_rates=letter_rates,
        notification_type=LETTER_TYPE,
        crown=True,
        letter_page_count=0,
        date=datetime.utcnow(),
    )
    assert letter_rate == 0


def test_fetch_monthly_billing_for_year(sample_service, sample_template, sample_ft_billing):
    service = sample_service()
    template = sample_template(service=service, template_type=SMS_TYPE)
    for i in range(1, 31):
        sample_ft_billing(
            utc_date='2018-06-{}'.format(i),
            service=service,
            template=template,
            notification_type=SMS_TYPE,
            rate_multiplier=2,
            rate=0.162,
        )
    for i in range(1, 32):
        sample_ft_billing(
            utc_date='2018-07-{}'.format(i), service=service, template=template, notification_type=SMS_TYPE, rate=0.158
        )

    results = fetch_monthly_billing_for_year(service.id, 2018)

    assert len(results) == 2
    assert str(results[0].month) == '2018-06-01'
    assert results[0].notifications_sent == 30
    assert results[0].billable_units == Decimal('60')
    assert results[0].rate == Decimal('0.162')
    assert results[0].notification_type == SMS_TYPE
    assert results[0].postage == 'none'

    assert str(results[1].month) == '2018-07-01'
    assert results[1].notifications_sent == 31
    assert results[1].billable_units == Decimal('31')
    assert results[1].rate == Decimal('0.158')
    assert results[1].notification_type == SMS_TYPE
    assert results[1].postage == 'none'


@freeze_time('2018-08-01 13:30:00')
def test_fetch_monthly_billing_for_year_adds_data_for_today(
    notify_db_session,
    sample_service,
    sample_template,
    sample_notification,
    sample_ft_billing,
):
    service = sample_service()
    template = sample_template(service=service, template_type=EMAIL_TYPE)
    for i in range(1, 32):
        sample_ft_billing(
            utc_date='2018-07-{}'.format(i),
            service=service,
            template=template,
            notification_type=EMAIL_TYPE,
            rate=0.162,
        )
    sample_notification(template=template, status=NOTIFICATION_DELIVERED)

    stmt = select(func.count()).select_from(FactBilling).where(FactBilling.service_id == service.id)

    assert notify_db_session.session.scalar(stmt) == 31
    results = fetch_monthly_billing_for_year(service.id, 2018)
    assert len(results) == 2
    assert notify_db_session.session.scalar(stmt) == 32


# This test assumes the local timezone is EST
def test_fetch_monthly_billing_for_year_return_financial_year(
    sample_service,
    sample_template,
    sample_ft_billing,
):
    service = set_up_yearly_data(sample_service, sample_template, sample_ft_billing, (1976, 1977))

    # returns 3 rows, per month, returns financial year april to end of march
    # Orders by Month
    results = fetch_monthly_billing_for_year(service.id, 1976)
    assert len(results) == 52

    assert str(results[0].month) == '1976-04-01'
    assert results[0].notification_type == EMAIL_TYPE
    assert results[0].notifications_sent == 30
    assert results[0].billable_units == 30
    assert results[0].rate == Decimal('0')

    assert str(results[1].month) == '1976-04-01'
    assert results[1].notification_type == LETTER_TYPE
    assert results[1].notifications_sent == 30
    assert results[1].billable_units == 30
    assert results[1].rate == Decimal('0.30')
    assert str(results[1].month) == '1976-04-01'

    assert results[2].notification_type == LETTER_TYPE
    assert results[2].notifications_sent == 30
    assert results[2].billable_units == 30
    assert results[2].rate == Decimal('0.33')
    assert str(results[3].month) == '1976-04-01'

    assert results[3].notification_type == SMS_TYPE
    assert results[3].notifications_sent == 30
    assert results[3].billable_units == 30
    assert results[3].rate == Decimal('0.162')

    assert str(results[4].month) == '1976-05-01'

    assert str(results[47].month) == '1977-03-01'


def test_fetch_billing_totals_for_year(
    sample_service,
    sample_template,
    sample_ft_billing,
):
    service = set_up_yearly_data(sample_service, sample_template, sample_ft_billing, (1974, 1975))
    results = fetch_billing_totals_for_year(service.id, 1974)

    assert len(results) == 4
    assert results[0].notification_type == EMAIL_TYPE
    assert results[0].notifications_sent == 365
    assert results[0].billable_units == 365
    assert results[0].rate == Decimal('0')

    assert results[1].notification_type == LETTER_TYPE
    assert results[1].notifications_sent == 365
    assert results[1].billable_units == 365
    assert results[1].rate == Decimal('0.3')

    assert results[2].notification_type == LETTER_TYPE
    assert results[2].notifications_sent == 365
    assert results[2].billable_units == 365
    assert results[2].rate == Decimal('0.33')

    assert results[3].notification_type == SMS_TYPE
    assert results[3].notifications_sent == 365
    assert results[3].billable_units == 365
    assert results[3].rate == Decimal('0.162')


def test_delete_billing_data(
    notify_db_session,
    sample_service,
    sample_template,
    sample_ft_billing,
):
    service_1 = sample_service()
    sms_template = sample_template(service=service_1, template_type=SMS_TYPE)
    email_template = sample_template(service=service_1, template_type=EMAIL_TYPE)

    service_2 = sample_service()
    other_service_template = sample_template(service=service_2, template_type=SMS_TYPE)

    existing_rows_to_delete = [  # noqa
        sample_ft_billing('2018-01-01', SMS_TYPE, sms_template, service_1, billable_unit=1),
        sample_ft_billing('2018-01-01', EMAIL_TYPE, email_template, service_1, billable_unit=2),
    ]
    other_day = sample_ft_billing('2018-01-02', SMS_TYPE, sms_template, service_1, billable_unit=3)
    other_service = sample_ft_billing('2018-01-01', SMS_TYPE, other_service_template, service_2, billable_unit=4)

    delete_billing_data_for_service_for_day('2018-01-01', service_1.id)

    stmt = select(FactBilling).where(FactBilling.service_id.in_((service_1.id, service_2.id)))
    current_rows = notify_db_session.session.scalars(stmt).all()

    assert sorted(x.billable_units for x in current_rows) == sorted(
        [other_day.billable_units, other_service.billable_units]
    )


def test_fetch_sms_free_allowance_remainder_with_two_services(
    sample_service,
    sample_template,
    sample_ft_billing,
    sample_annual_billing,
    sample_organisation,
):
    # This service has free allowance.
    service = sample_service()
    template = sample_template(service=service)
    org = sample_organisation(name=ORG_NAME.format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    sample_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2016)
    sample_ft_billing(
        service=service,
        template=template,
        utc_date=datetime(2016, 4, 20),
        notification_type=SMS_TYPE,
        billable_unit=2,
        rate=0.11,
    )
    sample_ft_billing(
        service=service,
        template=template,
        utc_date=datetime(2016, 5, 20),
        notification_type=SMS_TYPE,
        billable_unit=3,
        rate=0.11,
    )

    # This service used its free allowance.
    service_2 = sample_service()
    template_2 = sample_template(service=service_2)
    org_2 = sample_organisation(name=ORG_NAME.format(service_2.name))
    dao_add_service_to_organisation(service=service_2, organisation_id=org_2.id)
    sample_annual_billing(service_id=service_2.id, free_sms_fragment_limit=20, financial_year_start=2016)
    sample_ft_billing(
        service=service_2,
        template=template_2,
        utc_date=datetime(2016, 4, 20),
        notification_type=SMS_TYPE,
        billable_unit=12,
        rate=0.11,
    )
    sample_ft_billing(
        service=service_2,
        template=template_2,
        utc_date=datetime(2016, 4, 22),
        notification_type=SMS_TYPE,
        billable_unit=10,
        rate=0.11,
    )
    sample_ft_billing(
        service=service_2,
        template=template_2,
        utc_date=datetime(2016, 5, 20),
        notification_type=SMS_TYPE,
        billable_unit=3,
        rate=0.11,
    )
    results = db.session.execute(fetch_sms_free_allowance_remainder(datetime(2016, 5, 1))).all()
    assert len(results) == 2
    service_result = [row for row in results if row[0] == service.id]
    assert service_result[0] == (service.id, 10, 2, 8)
    service_2_result = [row for row in results if row[0] == service_2.id]
    assert service_2_result[0] == (service_2.id, 20, 22, 0)
