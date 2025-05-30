from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import delete, desc, select

from app import db
from app.dao.dao_utils import transactional
from app.models import InboundSms, Service, ServiceDataRetention, SMS_TYPE
from app.utils import midnight_n_days_ago


@transactional
def dao_create_inbound_sms(inbound_sms):
    db.session.add(inbound_sms)


def dao_get_inbound_sms_for_service(
    service_id,
    user_number=None,
    *,
    limit_days=None,
    limit=None,
):
    stmt = select(InboundSms).where(InboundSms.service_id == service_id).order_by(InboundSms.created_at.desc())

    if limit_days is not None:
        start_date = midnight_n_days_ago(limit_days)
        stmt = stmt.where(InboundSms.created_at >= start_date)

    if user_number:
        stmt = stmt.where(InboundSms.user_number == user_number)

    if limit:
        stmt = stmt.limit(limit)

    return db.session.scalars(stmt).all()


def dao_get_paginated_inbound_sms_for_service_for_public_api(
    service_id,
    older_than=None,
    page_size=None,
):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']

    filters = [InboundSms.service_id == service_id]

    if older_than:
        stmt = select(InboundSms.created_at).where(InboundSms.id == older_than)
        older_than_created_at = db.session.scalars(stmt).first()

        filters.append(InboundSms.created_at < older_than_created_at)

    stmt = select(InboundSms).where(*filters).order_by(desc(InboundSms.created_at))
    return db.paginate(stmt, per_page=page_size).items


def _delete_inbound_sms(
    datetime_to_delete_from,
    query_filter,
):
    """
    This function executes delete queries, but the calling code is responsible for committing the changes.
    """
    stmt = (
        delete(InboundSms)
        .where(InboundSms.created_at < datetime_to_delete_from, *query_filter)
        .execution_options(synchronize_session='fetch')
    )

    # set to nonzero just to enter the loop
    number_deleted = 1
    deleted = 0
    while number_deleted > 0:
        number_deleted = db.session.execute(stmt).rowcount
        deleted += number_deleted

    # Intentionally no commit of the deletes.
    return deleted


@statsd(namespace='dao')
@transactional
def delete_inbound_sms_older_than_retention():
    current_app.logger.info('Deleting inbound sms for services with flexible data retention')

    stmt = (
        select(ServiceDataRetention)
        .join(ServiceDataRetention.service)
        .join(Service.inbound_numbers)
        .where(ServiceDataRetention.notification_type == SMS_TYPE)
    )

    flexible_data_retention = db.session.scalars(stmt).all()

    deleted = 0
    for f in flexible_data_retention:
        n_days_ago = midnight_n_days_ago(f.days_of_retention)

        current_app.logger.info('Deleting inbound sms for service id: {}'.format(f.service_id))
        deleted += _delete_inbound_sms(n_days_ago, query_filter=[InboundSms.service_id == f.service_id])

    current_app.logger.info('Deleting inbound sms for services without flexible data retention')

    seven_days_ago = midnight_n_days_ago(7)

    deleted += _delete_inbound_sms(
        seven_days_ago,
        query_filter=[
            InboundSms.service_id.notin_(x.service_id for x in flexible_data_retention),
        ],
    )

    current_app.logger.info('Deleted {} inbound sms'.format(deleted))

    return deleted


def dao_get_inbound_sms_by_id(
    service_id,
    inbound_id,
):
    stmt = select(InboundSms).where(InboundSms.id == inbound_id, InboundSms.service_id == service_id)

    return db.session.scalars(stmt).one()
