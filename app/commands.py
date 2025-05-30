import csv
import functools
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import click
import flask
import itertools
from click_datetime import Datetime as click_dt
from flask import current_app, json
from notifications_utils.template import SMSMessageTemplate
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from notifications_utils.statsd_decorators import statsd

from app import db, encryption
from app.constants import DATETIME_FORMAT
from app.aws import s3
from app.celery.tasks import record_daily_sorted_counts
from app.celery.nightly_tasks import send_total_sent_notifications_to_performance_platform
from app.celery.service_callback_tasks import send_delivery_status_to_service
from app.config import QueueNames
from app.constants import NOTIFICATION_CREATED, KEY_TYPE_TEST, SMS_TYPE
from app.dao.fact_billing_dao import (
    delete_billing_data_for_service_for_day,
    fetch_billing_data_for_day,
    get_service_ids_that_need_billing_populated,
    update_fact_billing,
)
from app.dao.organisation_dao import dao_get_organisation_by_email_address, dao_add_service_to_organisation

from app.dao.provider_rates_dao import create_provider_rates as dao_create_provider_rates
from app.dao.service_callback_api_dao import get_service_delivery_status_callback_api_for_service
from app.dao.services_dao import (
    delete_service_and_all_associated_db_objects,
    dao_fetch_all_services_by_user,
    dao_fetch_service_by_id,
    dao_update_service,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import delete_model_user, delete_user_verify_codes
from app.models import (
    PROVIDERS,
    Notification,
    Organisation,
    Domain,
    Service,
    EmailBranding,
)
from app.model import User
from app.performance_platform.processing_time import send_processing_time_for_start_and_end
from app.utils import get_local_timezone_midnight_in_utc, get_midnight_for_day_before


@click.group(name='command', help='Additional commands')
def command_group():
    pass


class notify_command:
    def __init__(
        self,
        name=None,
    ):
        self.name = name

    def __call__(
        self,
        func,
    ):
        # we need to call the flask with_appcontext decorator to ensure the config is loaded, db connected etc etc.
        # we also need to use functools.wraps to carry through the names and docstrings etc of the functions.
        # Then we need to turn it into a click.Command - that's what command_group.add_command expects.
        @click.command(name=self.name)
        @functools.wraps(func)
        @flask.cli.with_appcontext
        def wrapper(
            *args,
            **kwargs,
        ):
            return func(*args, **kwargs)

        command_group.add_command(wrapper)

        return wrapper


@notify_command()
@click.option('-p', '--provider_name', required=True, type=click.Choice(PROVIDERS))
@click.option('-c', '--cost', required=True, help='Cost (pence) per message including decimals', type=float)
@click.option('-d', '--valid_from', required=True, type=click_dt(format='%Y-%m-%dT%H:%M:%S'))
def create_provider_rates(
    provider_name,
    cost,
    valid_from,
):
    """
    Backfill rates for a given provider
    """
    cost = Decimal(cost)
    dao_create_provider_rates(provider_name, valid_from, cost)


@notify_command()
@click.option(
    '-u',
    '--user_email_prefix',
    required=True,
    help="""
    Functional test user email prefix. eg "notify-test-preview"
""",
)  # noqa
def purge_functional_test_data(user_email_prefix):
    """
    Remove non-seeded functional test data

    users, services, etc. Give an email prefix. Probably "notify-test-preview".
    """

    stmt = select(User).where(User.email_address.like(f'{user_email_prefix}%'))
    users = db.session.scalars(stmt).all()

    for usr in users:
        # Make sure the full email includes a uuid in it
        # Just in case someone decides to use a similar email address.
        try:
            uuid.UUID(usr.email_address.split('@')[0].split('+')[1])
        except ValueError:
            print("Skipping {} as the user email doesn't contain a UUID.".format(usr.email_address))
        else:
            services = dao_fetch_all_services_by_user(usr.id)
            if services:
                for service in services:
                    delete_service_and_all_associated_db_objects(service)
            else:
                delete_user_verify_codes(usr)
                delete_model_user(usr)


@notify_command()
@click.option('-s', '--start_date', required=True, help='start date inclusive', type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help='end date inclusive', type=click_dt(format='%Y-%m-%d'))
def backfill_performance_platform_totals(
    start_date,
    end_date,
):
    """
    Send historical total messages sent to Performance Platform.

    WARNING: This does not overwrite existing data. You need to delete
             the existing data or Performance Platform will double-count.
    """

    delta = end_date - start_date

    print('Sending total messages sent for all days between {} and {}'.format(start_date, end_date))

    for i in range(delta.days + 1):
        process_date = start_date + timedelta(days=i)

        print('Sending total messages sent for {}'.format(process_date.isoformat()))

        send_total_sent_notifications_to_performance_platform(process_date)


@notify_command()
@click.option('-s', '--start_date', required=True, help='start date inclusive', type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help='end date inclusive', type=click_dt(format='%Y-%m-%d'))
def backfill_processing_time(
    start_date,
    end_date,
):
    """
    Send historical processing time to Performance Platform.
    """

    delta = end_date - start_date

    print('Sending notification processing-time data for all days between {} and {}'.format(start_date, end_date))

    for i in range(delta.days + 1):
        # because the tz conversion funcs talk about midnight, and the midnight before last,
        # we want to pretend we're running this from the next morning, so add one.
        process_date = start_date + timedelta(days=i + 1)

        process_start_date = get_midnight_for_day_before(process_date)
        process_end_date = get_local_timezone_midnight_in_utc(process_date)

        print(
            'Sending notification processing-time for {} - {}'.format(
                process_start_date.isoformat(), process_end_date.isoformat()
            )
        )
        send_processing_time_for_start_and_end(process_start_date, process_end_date)


@notify_command(name='list-routes')
def list_routes():
    """List URLs of all application routes."""
    for rule in sorted(current_app.url_map.iter_rules(), key=lambda r: r.rule):
        print('{:10} {}'.format(', '.join(rule.methods - set(['OPTIONS', 'HEAD'])), rule.rule))


@notify_command(name='insert-inbound-numbers')
@click.option(
    '-f',
    '--file_name',
    required=True,
    help="""Full path of the file to upload, file is a contains inbound numbers,
              one number per line. The number must have the format of 07... not 447....""",
)
def insert_inbound_numbers_from_file(file_name):
    print('Inserting inbound numbers from {}'.format(file_name))
    file = open(file_name)
    sql = "insert into inbound_numbers values('{}', '{}', 'mmg', null, True, now(), null);"

    for line in file:
        print(line)
        db.session.execute(sql.format(uuid.uuid4(), line.strip()))
        db.session.commit()
    file.close()


@notify_command(name='replay-service-callbacks')
@click.option(
    '-f',
    '--file_name',
    required=True,
    help="""Full path of the file to upload, file is a contains client references of
              notifications that need the status to be sent to the service.""",
)
@click.option('-s', '--service_id', required=True, help="""The service that the callbacks are for""")
def replay_service_callbacks(
    file_name,
    service_id,
    notification_status,
):
    # not updated for notification callback_url as it doesn't appear to be used
    print('Start send service callbacks for service: ', service_id)
    callback_api: DeliveryStatusCallbackApiData | None = get_service_delivery_status_callback_api_for_service(
        service_id=service_id, notification_status=notification_status
    )
    if callback_api is None:
        print(f'Callback api was not found for service: {service_id}')
        return

    errors = []
    notifications = []
    file = open(file_name)

    for ref in file:
        stmt = select(Notification).where(Notification.client_reference == ref.strip())

        try:
            notification = db.session.scalars(stmt).one()
            notifications.append(notification)
        except NoResultFound:
            errors.append(f'Reference: {ref} was not found in notifications.')

    for e in errors:
        print(e)
    if errors:
        raise Exception('Some notifications for the given references were not found')

    for n in notifications:
        data = {
            'notification_id': str(n.id),
            'notification_client_reference': n.client_reference,
            'notification_to': n.to,
            'notification_status': n.status,
            'notification_created_at': n.created_at.strftime(DATETIME_FORMAT),
            'notification_updated_at': n.updated_at.strftime(DATETIME_FORMAT),
            'notification_sent_at': n.sent_at.strftime(DATETIME_FORMAT),
            'notification_type': n.notification_type,
            'service_callback_api_url': callback_api.url,
            'service_callback_api_bearer_token': encryption.decrypt(callback_api._bearer_token),
        }
        encrypted_status_update = encryption.encrypt(data)
        send_delivery_status_to_service.apply_async(
            [callback_api.id, str(n.id), encrypted_status_update], queue=QueueNames.CALLBACKS
        )

    print(
        'Replay service status for service: {}. Sent {} notification status updates to the queue'.format(
            service_id, len(notifications)
        )
    )


def setup_commands(application):
    application.cli.add_command(command_group)


@notify_command(name='migrate-data-to-ft-billing')
@click.option('-s', '--start_date', required=True, help='start date inclusive', type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help='end date inclusive', type=click_dt(format='%Y-%m-%d'))
@statsd(namespace='tasks')
def migrate_data_to_ft_billing(
    start_date,
    end_date,
):
    current_app.logger.info('Billing migration from date {} to {}'.format(start_date, end_date))

    process_date = start_date
    total_updated = 0

    while process_date < end_date:
        start_time = datetime.utcnow()
        # migrate data into ft_billing, upserting the data if it the record already exists
        sql = """
            insert into ft_billing (bst_date, template_id, service_id, notification_type, provider, rate_multiplier,
                international, billable_units, notifications_sent, rate, postage, created_at)
                select bst_date, template_id, service_id, notification_type, provider, rate_multiplier, international,
                    sum(billable_units) as billable_units, sum(notifications_sent) as notification_sent,
                    case when notification_type = 'sms' then sms_rate else letter_rate end as rate, postage, created_at
                from (
                    select
                        n.id,
                        (n.created_at at time zone 'UTC' at time zone 'America/New_York')::timestamp::date as bst_date,
                        coalesce(n.template_id, '00000000-0000-0000-0000-000000000000') as template_id,
                        coalesce(n.service_id, '00000000-0000-0000-0000-000000000000') as service_id,
                        n.notification_type,
                        coalesce(n.sent_by, (
                        case
                        when notification_type = 'sms' then
                            coalesce(sent_by, 'unknown')
                        when notification_type = 'letter' then
                            coalesce(sent_by, 'dvla')
                        else
                            coalesce(sent_by, 'ses')
                        end )) as provider,
                        coalesce(n.rate_multiplier,1) as rate_multiplier,
                        s.crown,
                        coalesce((select rates.rate from rates
                        where n.notification_type = rates.notification_type and n.created_at > rates.valid_from
                        order by rates.valid_from desc limit 1), 0) as sms_rate,
                        coalesce((select l.rate from letter_rates l where n.billable_units = l.sheet_count
                        and s.crown = l.crown and n.postage = l.post_class and n.created_at >= l.start_date
                        and n.created_at < coalesce(l.end_date, now()) and n.notification_type='letter'), 0)
                        as letter_rate,
                        coalesce(n.international, false) as international,
                        n.billable_units,
                        1 as notifications_sent,
                        coalesce(n.postage, 'none') as postage,
                        now() as created_at
                    from public.notification_history n
                    left join services s on s.id = n.service_id
                    where n.key_type!='test'
                    and n.notification_status in
                    ('sending', 'sent', 'delivered', 'temporary-failure', 'permanent-failure', 'failed')
                    and n.created_at >= (date :start + time '00:00:00') at time zone 'America/New_York'
                    at time zone 'UTC'
                    and n.created_at < (date :end + time '00:00:00') at time zone 'America/New_York' at time zone 'UTC'
                    ) as individual_record
                group by bst_date, template_id, service_id, notification_type, provider, rate_multiplier, international,
                    sms_rate, letter_rate, postage, created_at
                order by bst_date
            on conflict on constraint ft_billing_pkey do update set
             billable_units = excluded.billable_units,
             notifications_sent = excluded.notifications_sent,
             rate = excluded.rate,
             updated_at = now()
            """

        result = db.session.execute(sql, {'start': process_date, 'end': process_date + timedelta(days=1)})
        db.session.commit()
        current_app.logger.info(
            'ft_billing: --- Completed took {}ms. Migrated {} rows for {}'.format(
                datetime.now() - start_time, result.rowcount, process_date
            )
        )

        process_date += timedelta(days=1)

        total_updated += result.rowcount
    current_app.logger.info('Total inserted/updated records = {}'.format(total_updated))


@notify_command(name='rebuild-ft-billing-for-day')
@click.option('-s', '--service_id', required=False, type=click.UUID)
@click.option(
    '-d', '--day', help='The date to recalculate, as YYYY-MM-DD', required=True, type=click_dt(format='%Y-%m-%d')
)
def rebuild_ft_billing_for_day(
    service_id,
    day,
):
    """
    Rebuild the data in ft_billing for the given service_id and date
    """

    def rebuild_ft_data(
        process_day,
        service,
    ):
        deleted_rows = delete_billing_data_for_service_for_day(process_day, service)
        current_app.logger.info(
            'deleted {} existing billing rows for {} on {}'.format(deleted_rows, service, process_day)
        )
        transit_data = fetch_billing_data_for_day(process_day=process_day, service_id=service)
        # transit_data = every row that should exist
        for data in transit_data:
            # upsert existing rows
            update_fact_billing(data, process_day)
        current_app.logger.info(
            'added/updated {} billing rows for {} on {}'.format(len(transit_data), service, process_day)
        )

    if service_id:
        # confirm the service exists
        dao_fetch_service_by_id(service_id)
        rebuild_ft_data(day, service_id)
    else:
        services = get_service_ids_that_need_billing_populated(
            get_local_timezone_midnight_in_utc(day), get_local_timezone_midnight_in_utc(day + timedelta(days=1))
        )
        for row in services:
            rebuild_ft_data(day, row.service_id)


@notify_command(name='migrate-data-to-ft-notification-status')
@click.option('-s', '--start_date', required=True, help='start date inclusive', type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help='end date inclusive', type=click_dt(format='%Y-%m-%d'))
@statsd(namespace='tasks')
def migrate_data_to_ft_notification_status(
    start_date,
    end_date,
):
    print('Notification statuses migration from date {} to {}'.format(start_date, end_date))

    process_date = start_date
    total_updated = 0

    while process_date < end_date:
        start_time = datetime.now()
        # migrate data into ft_notification_status and update if record already exists

        db.session.execute(
            'delete from ft_notification_status where bst_date = :process_date', {'process_date': process_date}
        )

        sql = """
            insert into ft_notification_status (bst_date, template_id, service_id, job_id, notification_type, key_type,
                notification_status, created_at, notification_count)
                select
                    (n.created_at at time zone 'UTC' at time zone 'America/New_York')::timestamp::date as bst_date,
                    coalesce(n.template_id, '00000000-0000-0000-0000-000000000000') as template_id,
                    n.service_id,
                    coalesce(n.job_id, '00000000-0000-0000-0000-000000000000') as job_id,
                    n.notification_type,
                    n.key_type,
                    n.notification_status,
                    now() as created_at,
                    count(*) as notification_count
                from notification_history n
                where n.created_at >= (date :start + time '00:00:00') at time zone 'America/New_York' at time zone 'UTC'
                    and n.created_at < (date :end + time '00:00:00') at time zone 'America/New_York' at time zone 'UTC'
                group by bst_date, template_id, service_id, job_id, notification_type, key_type, notification_status
                order by bst_date
            """
        result = db.session.execute(sql, {'start': process_date, 'end': process_date + timedelta(days=1)})
        db.session.commit()
        print(
            'ft_notification_status: --- Completed took {}ms. Migrated {} rows for {}.'.format(
                datetime.now() - start_time, result.rowcount, process_date
            )
        )
        process_date += timedelta(days=1)

        total_updated += result.rowcount
    print('Total inserted/updated records = {}'.format(total_updated))


@notify_command(name='populate-notification-postage')
@click.option(
    '-s', '--start_date', default=datetime(2017, 2, 1), help='start date inclusive', type=click_dt(format='%Y-%m-%d')
)
@statsd(namespace='tasks')
def populate_notification_postage(start_date):
    current_app.logger.info('populating historical notification postage')

    total_updated = 0

    while start_date < datetime.utcnow():
        # process in ten day chunks
        end_date = start_date + timedelta(days=10)

        sql = """
            UPDATE {}
            SET postage = 'second'
            WHERE notification_type = 'letter' AND
            postage IS NULL AND
            created_at BETWEEN :start AND :end
            """

        execution_start = datetime.utcnow()

        if end_date > datetime.utcnow() - timedelta(days=8):
            print('Updating notifications table as well')
            db.session.execute(sql.format('notifications'), {'start': start_date, 'end': end_date})

        result = db.session.execute(sql.format('notification_history'), {'start': start_date, 'end': end_date})
        db.session.commit()

        current_app.logger.info(
            'notification postage took {}ms. Migrated {} rows for {} to {}'.format(
                datetime.utcnow() - execution_start, result.rowcount, start_date, end_date
            )
        )

        start_date += timedelta(days=10)

        total_updated += result.rowcount

    current_app.logger.info('Total inserted/updated records = {}'.format(total_updated))


@notify_command(name='archive-jobs-created-between-dates')
@click.option('-s', '--start_date', required=True, help='start date inclusive', type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help='end date inclusive', type=click_dt(format='%Y-%m-%d'))
@statsd(namespace='tasks')
def update_jobs_archived_flag(
    start_date,
    end_date,
):
    current_app.logger.info('Archiving jobs created between {} to {}'.format(start_date, end_date))

    process_date = start_date
    total_updated = 0

    while process_date < end_date:
        start_time = datetime.utcnow()
        sql = """update
                    jobs set archived = true
                where
                    created_at >= (date :start + time '00:00:00') at time zone 'America/New_York'
                    at time zone 'UTC'
                    and created_at < (date :end + time '00:00:00') at time zone 'America/New_York' at time zone 'UTC'"""

        result = db.session.execute(sql, {'start': process_date, 'end': process_date + timedelta(days=1)})
        db.session.commit()
        current_app.logger.info(
            'jobs: --- Completed took {}ms. Archived {} jobs for {}'.format(
                datetime.now() - start_time, result.rowcount, process_date
            )
        )

        process_date += timedelta(days=1)

        total_updated += result.rowcount
    current_app.logger.info('Total archived jobs = {}'.format(total_updated))


@notify_command(name='update-emails-to-remove-gsi')
@click.option('-s', '--service_id', required=True, help='service id. Update all user.email_address to remove .gsi')
@statsd(namespace='tasks')
def update_emails_to_remove_gsi(service_id):
    users_to_update = """SELECT u.id user_id, u.name, email_address, s.id, s.name
                           FROM users u
                           JOIN user_to_service us on (u.id = us.user_id)
                           JOIN services s on (s.id = us.service_id)
                          WHERE s.id = :service_id
                            AND u.email_address ilike ('%.gsi.gov.uk%')
    """
    results = db.session.execute(users_to_update, {'service_id': service_id})
    print('Updating {} users.'.format(results.rowcount))

    for user in results:
        print('User with id {} updated'.format(user.user_id))

        update_stmt = """
        UPDATE users
           SET email_address = replace(replace(email_address, '.gsi.gov.uk', '.gov.uk'), '.GSI.GOV.UK', '.GOV.UK'),
               updated_at = now()
         WHERE id = :user_id
        """
        db.session.execute(update_stmt, {'user_id': str(user.user_id)})
        db.session.commit()


@notify_command(name='replay-daily-sorted-count-files')
@click.option('-f', '--file_extension', required=False, help='File extension to search for, defaults to rs.txt')
@statsd(namespace='tasks')
def replay_daily_sorted_count_files(file_extension):
    bucket_location = '{}-ftp'.format(current_app.config['NOTIFY_EMAIL_FROM_DOMAIN'])
    for filename in s3.get_list_of_files_by_suffix(
        bucket_name=bucket_location, subfolder='root/dispatch', suffix=file_extension or '.rs.txt'
    ):
        print('Create task to record daily sorted counts for file: ', filename)
        record_daily_sorted_counts.apply_async([filename], queue=QueueNames.NOTIFY)


@notify_command(name='populate-organisations-from-file')
@click.option(
    '-f',
    '--file_name',
    required=True,
    help='Pipe delimited file containing organisation name, sector, crown, argeement_signed, domains',
)
def populate_organisations_from_file(file_name):  # noqa: C901
    # [0] organisation name:: name of the organisation insert if organisation is missing.
    # [1] sector:: Central | Local | NHS only
    # [2] crown:: TRUE | FALSE only
    # [3] argeement_signed:: TRUE | FALSE
    # [4] domains:: comma separated list of domains related to the organisation
    # [5] email branding name: name of the default email branding for the org
    # [6] letter branding name: name of the default letter branding for the org

    # The expectation is that the organisation, organisation_to_service
    # and user_to_organisation will be cleared before running this command.
    # Ignoring duplicates allows us to run the command again with the same file or same file with new rows.
    with open(file_name, 'r') as f:

        def boolean_or_none(field):
            if field == '1':
                return True
            elif field == '0':
                return False
            elif field == '':
                return None

        for line in itertools.islice(f, 1, None):
            columns = line.split('|')
            print(columns)
            email_branding = None
            email_branding_column = columns[5].strip()
            if len(email_branding_column) > 0:
                stmt = select(EmailBranding).where(EmailBranding.name == email_branding_column)
                email_branding = db.session.scalars(stmt).one()
            data = {
                'name': columns[0],
                'active': True,
                'agreement_signed': boolean_or_none(columns[3]),
                'crown': boolean_or_none(columns[2]),
                'organisation_type': columns[1].lower(),
                'email_branding_id': email_branding.id if email_branding else None,
            }
            org = Organisation(**data)
            try:
                db.session.add(org)
                db.session.commit()
            except IntegrityError:
                print('duplicate org', org.name)
                db.session.rollback()
            domains = columns[4].split(',')
            for d in domains:
                if len(d.strip()) > 0:
                    domain = Domain(domain=d.strip(), organisation_id=org.id)
                    try:
                        db.session.add(domain)
                        db.session.commit()
                    except IntegrityError:
                        print('duplicate domain', d.strip())
                        db.session.rollback()


@notify_command(name='get-letter-details-from-zips-sent-file')
@click.argument('file_paths', required=True, nargs=-1)
@statsd(namespace='tasks')
def get_letter_details_from_zips_sent_file(file_paths):
    """Get notification details from letters listed in zips_sent file(s)

    This takes one or more file paths for the zips_sent files in S3 as its parameters, for example:
    get-letter-details-from-zips-sent-file '2019-04-01/zips_sent/filename_1' '2019-04-01/zips_sent/filename_2'
    """

    rows_from_file = []

    for path in file_paths:
        file_contents = s3.get_s3_file(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'], file_location=path)
        rows_from_file.extend(json.loads(file_contents))

    notification_references = tuple(row[18:34] for row in rows_from_file)

    sql = """
        SELECT id, service_id, reference, job_id, created_at
        FROM notifications
        WHERE reference IN :notification_references
        ORDER BY service_id, job_id"""
    result = db.session.execute(sql, {'notification_references': notification_references}).fetchall()

    with open('zips_sent_details.csv', 'w') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['notification_id', 'service_id', 'reference', 'job_id', 'created_at'])

        for row in result:
            csv_writer.writerow(row)


@notify_command(name='associate-services-to-organisations')
def associate_services_to_organisations():
    service_history_model = Service.get_history_model()
    stmt = select(service_history_model).where(service_history_model.version == 1)
    services = db.session.scalars(stmt).all()

    for s in services:
        stmt = select(User).where(User.id == s.created_by_id)
        created_by_user = db.session.scalars(stmt).first()

        organisation = dao_get_organisation_by_email_address(created_by_user.email_address)
        service = dao_fetch_service_by_id(service_id=s.id)
        if organisation:
            dao_add_service_to_organisation(service=service, organisation_id=organisation.id)

    print('finished associating services to organisations')


@notify_command(name='populate-service-volume-intentions')
@click.option('-f', '--file_name', required=True, help='Pipe delimited file containing service_id, SMS, email, letters')
def populate_service_volume_intentions(file_name):
    # [0] service_id
    # [1] SMS:: volume intentions for service
    # [2] Email:: volume intentions for service
    # [3] Letters:: volume intentions for service

    with open(file_name, 'r') as f:
        for line in itertools.islice(f, 1, None):
            columns = line.split(',')
            print(columns)
            service = dao_fetch_service_by_id(columns[0])
            service.volume_sms = columns[1]
            service.volume_email = columns[2]
            service.volume_letter = columns[3]
            dao_update_service(service)
    print('populate-service-volume-intentions complete')


@notify_command(name='fix-billable-units')
def fix_billable_units():
    stmt = select(Notification).where(
        Notification.notification_type == SMS_TYPE,
        Notification.status != NOTIFICATION_CREATED,
        Notification.sent_at.is_(None),
        Notification.billable_units == 0,
        Notification.key_type != KEY_TYPE_TEST,
    )

    for notification in db.session.scalars(stmt).all():
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=notification.service.name,
            show_prefix=notification.service.prefix_sms,
        )
        print('Updating notification: {} with {} billable_units'.format(notification.id, template.fragment_count))

        stmt = (
            update(Notification)
            .where(Notification.id == notification.id)
            .values(billable_units=template.fragment_count)
        )

        db.session.execute(stmt)

    db.session.commit()
    print('End fix_billable_units')
