from app import db
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS,
    SMS_TYPE,
)
from app.dao.date_util import get_financial_year, get_financial_year_for_datetime
from app.models import (
    AnnualBilling,
    FactBilling,
    LetterRate,
    Notification,
    NotificationHistory,
    Rate,
    Service,
    ServiceSmsSender,
    Template,
)
from app.utils import get_local_timezone_midnight_in_utc
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from flask import current_app
from notifications_utils.timezones import convert_local_timezone_to_utc, convert_utc_to_local_timezone
from sqlalchemy import func, case, delete, desc, Date, Integer, and_, select, union_all
from sqlalchemy.dialects.postgresql import insert
from typing import Optional, Union
from uuid import UUID


def fetch_sms_free_allowance_remainder(start_date):
    """
    Note that this function returns a query expression; not rows.
    """

    # ASSUMPTION: AnnualBilling has been populated for year.
    billing_year = get_financial_year_for_datetime(start_date)
    start_of_year = date(billing_year, 4, 1)

    billable_units = func.coalesce(func.sum(FactBilling.billable_units * FactBilling.rate_multiplier), 0)

    return (
        select(
            AnnualBilling.service_id.label('service_id'),
            AnnualBilling.free_sms_fragment_limit,
            billable_units.label('billable_units'),
            func.greatest((AnnualBilling.free_sms_fragment_limit - billable_units).cast(Integer), 0).label(
                'sms_remainder'
            ),
        )
        .outerjoin(
            # if there are no ft_billing rows for a service we still want to return the annual billing so we can use the
            # free_sms_fragment_limit)
            FactBilling,
            and_(
                AnnualBilling.service_id == FactBilling.service_id,
                FactBilling.bst_date >= start_of_year,
                FactBilling.bst_date < start_date,
                FactBilling.notification_type == SMS_TYPE,
            ),
        )
        .where(
            AnnualBilling.financial_year_start == billing_year,
        )
        .group_by(
            AnnualBilling.service_id,
            AnnualBilling.free_sms_fragment_limit,
        )
    )


def fetch_nightly_billing_counts(process_day: date):
    """
    This function can also take a datetime instance because
    isinstance(<datetime instance>, date) is True.
    """

    # If process_day is a datetime instance, datetime.combine ignores the arguments after the first.
    start_date = convert_local_timezone_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_local_timezone_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))

    billable_type_list = {SMS_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE}

    stmt = (
        select(
            Service.name.label('service_name'),
            Notification.service_id.label('service_id'),
            Template.name.label('template_name'),
            Notification.template_id.label('template_id'),
            ServiceSmsSender.sms_sender.label('sender'),
            Notification.sms_sender_id.label('sender_id'),
            Notification.billing_code.label('billing_code'),
            func.count().label('count'),
            Notification.notification_type.label('channel_type'),
            func.sum(Notification.segments_count).label('total_message_parts'),
            func.sum(Notification.cost_in_millicents).label('total_cost'),
        )
        .where(
            Notification.status.in_(billable_type_list[SMS_TYPE]),
            Notification.key_type != KEY_TYPE_TEST,
            Notification.created_at >= start_date,
            Notification.created_at < end_date,
            Notification.notification_type == SMS_TYPE,
            Notification.cost_in_millicents > 0.0,
        )
        .group_by(
            Service.name,
            Notification.service_id,
            Template.name,
            Notification.template_id,
            ServiceSmsSender.sms_sender,
            Notification.sms_sender_id,
            Notification.billing_code,
            Notification.notification_type,
        )
        .join(Service, Notification.service_id == Service.id)
        .join(Template, Notification.template_id == Template.id)
        .join(ServiceSmsSender, Notification.sms_sender_id == ServiceSmsSender.id)
    )

    return db.session.execute(stmt).all()


def fetch_billing_totals_for_year(
    service_id,
    year,
):
    year_start_date, year_end_date = get_financial_year(year)

    """
      Billing for email: only record the total number of emails.
      Billing for letters: The billing units is used to fetch the correct rate for the sheet count of the letter.
      Total cost is notifications_sent * rate.
      Rate multiplier does not apply to email or letters.
    """
    email_and_letters_stmt = (
        select(
            func.sum(FactBilling.notifications_sent).label('notifications_sent'),
            func.sum(FactBilling.notifications_sent).label('billable_units'),
            FactBilling.rate.label('rate'),
            FactBilling.notification_type.label('notification_type'),
        )
        .where(
            FactBilling.service_id == service_id,
            FactBilling.bst_date >= year_start_date.strftime('%Y-%m-%d'),
            # This works only for timezones to the west of GMT
            FactBilling.bst_date < year_end_date.strftime('%Y-%m-%d'),
            FactBilling.notification_type.in_([EMAIL_TYPE, LETTER_TYPE]),
        )
        .group_by(FactBilling.rate, FactBilling.notification_type)
    )

    """
    Billing for SMS using the billing_units * rate_multiplier. Billing unit of SMS is the fragment count of a message
    """
    sms_stmt = (
        select(
            func.sum(FactBilling.notifications_sent).label('notifications_sent'),
            func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label('billable_units'),
            FactBilling.rate,
            FactBilling.notification_type,
        )
        .where(
            FactBilling.service_id == service_id,
            FactBilling.bst_date >= year_start_date.strftime('%Y-%m-%d'),
            FactBilling.bst_date
            < year_end_date.strftime('%Y-%m-%d'),  # This works only for timezones to the west of GMT
            FactBilling.notification_type == SMS_TYPE,
        )
        .group_by(FactBilling.rate, FactBilling.notification_type)
    )

    return db.session.execute(union_all(email_and_letters_stmt, sms_stmt).order_by('notification_type', 'rate')).all()


def fetch_monthly_billing_for_year(
    service_id: str,
    year,
):
    year_start_date, year_end_date = get_financial_year(year)
    utcnow = datetime.utcnow()
    today = convert_utc_to_local_timezone(utcnow)
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date >= today:
        yesterday = today - timedelta(days=1)
        for day in [yesterday, today]:
            data = fetch_billing_data_for_day(process_day=day, service_id=service_id)
            for d in data:
                update_fact_billing(data=d, process_day=day)

    email_and_letters_stmt = (
        select(
            func.date_trunc('month', FactBilling.bst_date).cast(Date).label('month'),
            func.sum(FactBilling.notifications_sent).label('notifications_sent'),
            func.sum(FactBilling.notifications_sent).label('billable_units'),
            FactBilling.rate.label('rate'),
            FactBilling.notification_type.label('notification_type'),
            FactBilling.postage,
        )
        .where(
            FactBilling.service_id == service_id,
            FactBilling.bst_date >= year_start_date.strftime('%Y-%m-%d'),
            FactBilling.bst_date <= year_end_date.strftime('%Y-%m-%d'),
            FactBilling.notification_type.in_([EMAIL_TYPE, LETTER_TYPE]),
        )
        .group_by('month', FactBilling.rate, FactBilling.notification_type, FactBilling.postage)
    )

    sms_stmt = (
        select(
            func.date_trunc('month', FactBilling.bst_date).cast(Date).label('month'),
            func.sum(FactBilling.notifications_sent).label('notifications_sent'),
            func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label('billable_units'),
            FactBilling.rate,
            FactBilling.notification_type,
            FactBilling.postage,
        )
        .where(
            FactBilling.service_id == service_id,
            FactBilling.bst_date >= year_start_date.strftime('%Y-%m-%d'),
            FactBilling.bst_date <= year_end_date.strftime('%Y-%m-%d'),
            FactBilling.notification_type == SMS_TYPE,
        )
        .group_by('month', FactBilling.rate, FactBilling.notification_type, FactBilling.postage)
    )

    return db.session.execute(
        union_all(email_and_letters_stmt, sms_stmt).order_by('month', 'notification_type', 'rate')
    ).all()


def delete_billing_data_for_service_for_day(
    process_day,
    service_id,
) -> int:
    """
    Delete all ft_billing data for a given service on a given bst_date, and return how many rows were deleted.
    """

    stmt = delete(FactBilling).where(FactBilling.bst_date == process_day, FactBilling.service_id == service_id)

    rows_deleted = db.session.execute(stmt).rowcount
    db.session.commit()
    return rows_deleted


def fetch_billing_data_for_day(
    process_day,
    service_id: Optional[Union[str, Iterable[str], UUID, Iterable[UUID]]] = None,
):
    """
    service_id can be a single ID or an iterable of IDs.
    """

    start_date = convert_local_timezone_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_local_timezone_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))
    # use notification_history if process day is older than 7 days
    # this is useful if we need to rebuild the ft_billing table for a date older than 7 days ago.
    current_app.logger.info('Populate ft_billing for %s to %s', start_date, end_date)
    transit_data = []

    if not service_id:
        # This includes None and empty iterables.
        service_ids = [x.id for x in db.session.scalars(select(Service)).all()]
    else:
        service_ids = (service_id,) if isinstance(service_id, (str, UUID)) else service_id

    for id_of_service in service_ids:
        for notification_type in (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE):
            results = _query_for_billing_data(
                table=Notification,
                notification_type=notification_type,
                start_date=start_date,
                end_date=end_date,
                service_id=id_of_service,
            )

            # If data has been purged from Notification, use NotificationHistory.
            if len(results) == 0:
                results = _query_for_billing_data(
                    table=NotificationHistory,
                    notification_type=notification_type,
                    start_date=start_date,
                    end_date=end_date,
                    service_id=id_of_service,
                )

            transit_data.extend(results)

    return transit_data


def _query_for_billing_data(
    table,
    notification_type,
    start_date,
    end_date,
    service_id,
):
    billable_type_list = {
        SMS_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE,
        EMAIL_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE,
        LETTER_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS,
    }

    stmt = (
        select(
            table.template_id,
            table.service_id,
            table.notification_type,
            func.coalesce(
                table.sent_by,
                case(
                    [
                        (table.notification_type == LETTER_TYPE, 'dvla'),
                        (table.notification_type == SMS_TYPE, 'unknown'),
                        (table.notification_type == EMAIL_TYPE, 'ses'),
                    ]
                ),
            ).label('sent_by'),
            func.coalesce(table.rate_multiplier, 1).cast(Integer).label('rate_multiplier'),
            func.coalesce(table.international, False).label('international'),
            case(
                [
                    (table.notification_type == LETTER_TYPE, table.billable_units),
                ]
            ).label('letter_page_count'),
            func.sum(table.billable_units).label('billable_units'),
            func.count().label('notifications_sent'),
            Service.crown,
            func.coalesce(table.postage, 'none').label('postage'),
        )
        .where(
            table.status.in_(billable_type_list[notification_type]),
            table.key_type != KEY_TYPE_TEST,
            table.created_at >= start_date,
            table.created_at < end_date,
            table.notification_type == notification_type,
            table.service_id == service_id,
        )
        .group_by(
            table.template_id,
            table.service_id,
            table.notification_type,
            'sent_by',
            'letter_page_count',
            table.rate_multiplier,
            table.international,
            Service.crown,
            table.postage,
        )
        .join(Service)
    )

    return db.session.execute(stmt).all()


def get_rates_for_billing():
    non_letter_rates = db.session.scalars(select(Rate).order_by(desc(Rate.valid_from))).all()
    letter_rates = db.session.scalars(select(LetterRate).order_by(desc(LetterRate.start_date))).all()
    return non_letter_rates, letter_rates


def get_service_ids_that_need_billing_populated(
    start_date,
    end_date,
):
    stmt = (
        select(NotificationHistory.service_id)
        .where(
            NotificationHistory.created_at >= start_date,
            NotificationHistory.created_at <= end_date,
            NotificationHistory.notification_type.in_([SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]),
            NotificationHistory.billable_units != 0,
        )
        .distinct()
    )

    return db.session.scalars(stmt).all()


def get_rate(
    non_letter_rates, letter_rates, notification_type, date, crown=None, letter_page_count=None, post_class='second'
):
    start_of_day = get_local_timezone_midnight_in_utc(date)

    if notification_type == LETTER_TYPE:
        if letter_page_count == 0:
            return 0
        return next(
            r.rate
            for r in letter_rates
            if (
                start_of_day >= r.start_date
                and crown == r.crown
                and letter_page_count == r.sheet_count
                and post_class == r.post_class
            )
        )
    elif notification_type == SMS_TYPE:
        return next(
            r.rate
            for r in non_letter_rates
            if (notification_type == r.notification_type and start_of_day >= r.valid_from)
        )
    else:
        return 0


def update_fact_billing(
    data,
    process_day,
):
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(
        non_letter_rates,
        letter_rates,
        data.notification_type,
        process_day,
        data.crown,
        data.letter_page_count,
        data.postage,
    )
    billing_record = create_billing_record(data, rate, process_day)

    table = FactBilling.__table__
    """
       This uses the Postgres upsert to avoid race conditions when two threads try to insert
       at the same row. The excluded object refers to values that we tried to insert but were
       rejected.
       http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    """
    stmt = insert(table).values(
        bst_date=billing_record.bst_date,
        template_id=billing_record.template_id,
        service_id=billing_record.service_id,
        provider=billing_record.provider,
        rate_multiplier=billing_record.rate_multiplier,
        notification_type=billing_record.notification_type,
        international=billing_record.international,
        billable_units=billing_record.billable_units,
        notifications_sent=billing_record.notifications_sent,
        rate=billing_record.rate,
        postage=billing_record.postage,
    )

    stmt = stmt.on_conflict_do_update(
        constraint='ft_billing_pkey',
        set_={
            'notifications_sent': stmt.excluded.notifications_sent,
            'billable_units': stmt.excluded.billable_units,
            'updated_at': datetime.utcnow(),
        },
    )
    db.session.connection().execute(stmt)
    db.session.commit()


def create_billing_record(
    data,
    rate,
    process_day,
):
    billing_record = FactBilling(
        bst_date=process_day,
        template_id=data.template_id,
        service_id=data.service_id,
        notification_type=data.notification_type,
        provider=data.sent_by,
        rate_multiplier=data.rate_multiplier,
        international=data.international,
        billable_units=data.billable_units,
        notifications_sent=data.notifications_sent,
        rate=rate,
        postage=data.postage,
    )
    return billing_record
