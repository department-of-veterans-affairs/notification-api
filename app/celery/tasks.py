from datetime import datetime
from collections import namedtuple, defaultdict

from flask import current_app
from notifications_utils.recipients import RecipientCSV
from notifications_utils.statsd_decorators import statsd
from notifications_utils.template import (
    SMSMessageTemplate,
    WithSubjectTemplate,
)
from notifications_utils.timezones import convert_utc_to_local_timezone
from sqlalchemy.exc import SQLAlchemyError

from app import (
    create_random_identifier,
    encryption,
    notify_celery,
)
from app.aws import s3
from app.celery import provider_tasks, research_mode_tasks
from app.config import QueueNames
from app.constants import (
    DVLA_RESPONSE_STATUS_SENT,
    EMAIL_TYPE,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
)
from app.dao.daily_sorted_letter_dao import dao_create_or_update_daily_sorted_letter
from app.dao.jobs_dao import (
    dao_update_job,
    dao_get_job_by_id,
)
from app.dao.notifications_dao import (
    get_notification_by_id,
    dao_update_notifications_by_reference,
    dao_get_last_notification_added_for_job_id,
    update_notification_status_by_reference,
    dao_get_notification_history_by_reference,
)
from app.dao.service_sms_sender_dao import (
    dao_get_service_sms_sender_by_id,
    dao_get_service_sms_sender_by_service_id_and_number,
)
from app.dao.services_dao import dao_fetch_service_by_id, fetch_todays_total_message_count
from app.dao.templates_dao import dao_get_template_by_id
from app.exceptions import DVLAException
from app.models import DailySortedLetter
from app.notifications.process_notifications import persist_notification
from app.service.utils import service_allowed_to_send_to
from app.utils import create_uuid


@notify_celery.task(name='process-job')
@statsd(namespace='tasks')
def process_job(
    job_id,
    sender_id=None,
):
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)

    if job.job_status != JOB_STATUS_PENDING:
        return

    service = job.service

    if not service.active:
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        current_app.logger.warning('Job %s has been cancelled, service %s is inactive', job_id, service.id)
        return

    if __sending_limits_for_job_exceeded(service, job, job_id):
        return

    job.job_status = JOB_STATUS_IN_PROGRESS
    job.processing_started = start
    dao_update_job(job)

    db_template = dao_get_template_by_id(job.template_id, job.template_version)

    TemplateClass = get_template_class(db_template.template_type)
    template = TemplateClass(db_template.__dict__)

    current_app.logger.debug('Starting job %s processing %s notifications', job_id, job.notification_count)

    for row in RecipientCSV(
        s3.get_job_from_s3(str(service.id), str(job_id)),
        template_type=template.template_type,
        placeholders=template.placeholder_names,
    ).get_rows():
        process_row(row, template, job, service, sender_id=sender_id)

    job_complete(job, start=start)


def job_complete(
    job,
    resumed=False,
    start=None,
):
    job.job_status = JOB_STATUS_FINISHED

    finished = datetime.utcnow()
    job.processing_finished = finished
    dao_update_job(job)

    if resumed:
        current_app.logger.info('Resumed Job %s completed at %s', job.id, job.created_at)
    else:
        current_app.logger.info(
            'Job %s created at %s started at %s finished at %s', job.id, job.created_at, start, finished
        )


def process_row(
    row,
    template,
    job,
    service,
    sender_id=None,
):
    template_type = template.template_type
    encrypted = encryption.encrypt(
        {
            'template': str(template.id),
            'template_version': job.template_version,
            'job': str(job.id),
            'to': row.recipient,
            'row_number': row.index,
            'personalisation': dict(row.personalisation),
        }
    )

    send_fns = {SMS_TYPE: save_sms, EMAIL_TYPE: save_email, LETTER_TYPE: save_letter}

    send_fn = send_fns[template_type]

    task_kwargs = {}
    if sender_id:
        task_kwargs['sender_id'] = sender_id

    send_fn.apply_async(
        (
            str(service.id),
            create_uuid(),
            encrypted,
        ),
        task_kwargs,
        queue=QueueNames.NOTIFY,
    )


def __sending_limits_for_job_exceeded(
    service,
    job,
    job_id,
):
    total_sent = fetch_todays_total_message_count(service.id)

    if total_sent + job.notification_count > service.message_limit:
        job.job_status = 'sending limits exceeded'
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.info(
            'Job %s size %s error. Sending limits %s exceeded', job_id, job.notification_count, service.message_limit
        )
        return True
    return False


@notify_celery.task(bind=True, name='save-sms', max_retries=5, default_retry_delay=300)
@statsd(namespace='tasks')
def save_sms(
    self,
    service_id,
    notification_id,
    encrypted_notification,
    sender_id=None,
):
    notification = encryption.decrypt(encrypted_notification)
    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id(notification['template'], version=notification['template_version'])

    if sender_id:
        reply_to_text = dao_get_service_sms_sender_by_id(str(service_id), str(sender_id)).sms_sender
    else:
        reply_to_text = template.get_reply_to_text()

    if not service_allowed_to_send_to(notification['to'], service, KEY_TYPE_NORMAL):
        current_app.logger.debug('SMS %s failed as restricted service', notification_id)
        return

    try:
        saved_notification = persist_notification(
            template_id=notification['template'],
            template_version=notification['template_version'],
            recipient=notification['to'],
            service_id=service_id,
            personalisation=notification.get('personalisation'),
            notification_type=SMS_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification.get('job', None),
            job_row_number=notification.get('row_number', None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
        )

        sms_sender = dao_get_service_sms_sender_by_service_id_and_number(
            notification.get(service_id),
            str(notification.get(reply_to_text)),
        )

        if sms_sender and sms_sender.rate_limit:
            provider_tasks.deliver_sms_with_rate_limiting.apply_async(
                args=(),
                kwargs={'notification_id': str(saved_notification.id)},
                queue=QueueNames.SEND_SMS if not service.research_mode else QueueNames.NOTIFY,
            )
        else:
            provider_tasks.deliver_sms.apply_async(
                args=(),
                kwargs={'notification_id': str(saved_notification.id)},
                queue=QueueNames.SEND_SMS if not service.research_mode else QueueNames.NOTIFY,
            )

        current_app.logger.debug(
            'SMS %s created at %s for job %s',
            saved_notification.id,
            saved_notification.created_at,
            notification.get('job', None),
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name='save-email', max_retries=5, default_retry_delay=300)
@statsd(namespace='tasks')
def save_email(
    self,
    service_id,
    notification_id,
    encrypted_notification,
):
    notification = encryption.decrypt(encrypted_notification)

    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id(notification['template'], version=notification['template_version'])

    reply_to_text = template.get_reply_to_text()

    if not service_allowed_to_send_to(notification['to'], service, KEY_TYPE_NORMAL):
        current_app.logger.info('Email %s failed as restricted service', notification_id)
        return

    try:
        saved_notification = persist_notification(
            template_id=notification['template'],
            template_version=notification['template_version'],
            recipient=notification['to'],
            service_id=service_id,
            personalisation=notification.get('personalisation'),
            notification_type=EMAIL_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification.get('job', None),
            job_row_number=notification.get('row_number', None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
        )

        provider_tasks.deliver_email.apply_async(
            args=(),
            kwargs={'notification_id': str(saved_notification.id)},
            queue=QueueNames.SEND_EMAIL if not service.research_mode else QueueNames.NOTIFY,
        )

        current_app.logger.debug('Email %s created at %s', saved_notification.id, saved_notification.created_at)
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(bind=True, name='save-letter', max_retries=5, default_retry_delay=300)
@statsd(namespace='tasks')
def save_letter(
    self,
    service_id,
    notification_id,
    encrypted_notification,
):
    notification = encryption.decrypt(encrypted_notification)

    # we store the recipient as just the first item of the person's address
    recipient = notification['personalisation']['addressline1']

    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id(notification['template'], version=notification['template_version'])

    try:
        # if we don't want to actually send the letter, then start it off in SENDING so we don't pick it up
        status = NOTIFICATION_CREATED if not service.research_mode else NOTIFICATION_SENDING

        saved_notification = persist_notification(
            template_id=notification['template'],
            template_version=notification['template_version'],
            template_postage=template.postage,
            recipient=recipient,
            service_id=service_id,
            personalisation=notification['personalisation'],
            notification_type=LETTER_TYPE,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification['job'],
            job_row_number=notification['row_number'],
            notification_id=notification_id,
            reference=create_random_identifier(),
            reply_to_text=template.get_reply_to_text(),
            status=status,
        )
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['preview', 'development']:
            research_mode_tasks.create_fake_letter_response_file.apply_async(
                (saved_notification.reference,),
                queue=QueueNames.NOTIFY,
            )
        else:
            update_notification_status_by_reference(saved_notification.reference, 'delivered')

        current_app.logger.debug('Letter %s created at %s', saved_notification.id, saved_notification.created_at)
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


def handle_exception(
    task,
    notification,
    notification_id,
    exc,
):
    if not get_notification_by_id(notification_id):
        retry_msg = '{task} notification for job {job} row number {row} and notification id {noti}'.format(
            task=task.__name__,
            job=notification.get('job', None),
            row=notification.get('row_number', None),
            noti=notification_id,
        )
        # Sometimes, SQS plays the same message twice. We should be able to catch an IntegrityError, but it seems
        # SQLAlchemy is throwing a FlushError. So we check if the notification id already exists then do not
        # send to the retry queue.
        current_app.logger.exception('Retry %s', retry_msg)
        try:
            task.retry(queue=QueueNames.RETRY, exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.error('Max retry failed %s', retry_msg)


def get_template_class(template_type):
    if template_type == SMS_TYPE:
        return SMSMessageTemplate
    elif template_type in (EMAIL_TYPE, LETTER_TYPE):
        # since we don't need rendering capabilities (we only need to extract placeholders) both email and letter can
        # use the same base template
        return WithSubjectTemplate


@notify_celery.task(bind=True, name='update-letter-notifications-statuses')
@statsd(namespace='tasks')
def update_letter_notifications_statuses(
    self,
    filename,
):
    notification_updates = parse_dvla_file(filename)

    temporary_failures = []

    for update in notification_updates:
        check_billable_units(update)
        update_letter_notification(filename, temporary_failures, update)
    if temporary_failures:
        # This will alert Notify that DVLA was unable to deliver the letters, we need to investigate
        message = 'DVLA response file: {filename} has failed letters with notification.reference {failures}'.format(
            filename=filename, failures=temporary_failures
        )
        raise DVLAException(message)


@notify_celery.task(bind=True, name='record-daily-sorted-counts')
@statsd(namespace='tasks')
def record_daily_sorted_counts(
    self,
    filename,
):
    sorted_letter_counts = defaultdict(int)
    notification_updates = parse_dvla_file(filename)
    for update in notification_updates:
        sorted_letter_counts[update.cost_threshold.lower()] += 1

    unknown_status = sorted_letter_counts.keys() - {'unsorted', 'sorted'}
    if unknown_status:
        message = 'DVLA response file: {} contains unknown Sorted status {}'.format(filename, unknown_status.__repr__())
        raise DVLAException(message)

    billing_date = get_billing_date_in_est_from_filename(filename)
    persist_daily_sorted_letter_counts(day=billing_date, file_name=filename, sorted_letter_counts=sorted_letter_counts)


def parse_dvla_file(filename):
    bucket_location = '{}-ftp'.format(current_app.config['NOTIFY_EMAIL_FROM_DOMAIN'])
    response_file_content = s3.get_s3_file(bucket_location, filename)

    try:
        return process_updates_from_file(response_file_content)
    except TypeError:
        raise DVLAException('DVLA response file: {} has an invalid format'.format(filename))


def get_billing_date_in_est_from_filename(filename):
    # exclude seconds from the date since we don't need it. We got a date ending in 60 second - which is not valid.
    datetime_string = filename.split('-')[1][:-2]
    datetime_obj = datetime.strptime(datetime_string, '%Y%m%d%H%M')
    return convert_utc_to_local_timezone(datetime_obj).date()


def persist_daily_sorted_letter_counts(
    day,
    file_name,
    sorted_letter_counts,
):
    daily_letter_count = DailySortedLetter(
        billing_day=day,
        file_name=file_name,
        unsorted_count=sorted_letter_counts['unsorted'],
        sorted_count=sorted_letter_counts['sorted'],
    )
    dao_create_or_update_daily_sorted_letter(daily_letter_count)


def process_updates_from_file(response_file):
    NotificationUpdate = namedtuple('NotificationUpdate', ['reference', 'status', 'page_count', 'cost_threshold'])
    notification_updates = [NotificationUpdate(*line.split('|')) for line in response_file.splitlines()]
    return notification_updates


def update_letter_notification(
    filename,
    temporary_failures,
    update,
):
    if update.status == DVLA_RESPONSE_STATUS_SENT:
        status = NOTIFICATION_DELIVERED
    else:
        status = NOTIFICATION_TEMPORARY_FAILURE
        temporary_failures.append(update.reference)

    updated_count, _ = dao_update_notifications_by_reference(
        references=[update.reference], update_dict={'status': status, 'updated_at': datetime.utcnow()}
    )

    if not updated_count:
        msg = (
            'Update letter notification file {filename} failed: notification either not found '
            'or already updated from delivered. Status {status} for notification reference {reference}'.format(
                filename=filename, status=status, reference=update.reference
            )
        )
        current_app.logger.info(msg)


def check_billable_units(notification_update):
    notification = dao_get_notification_history_by_reference(notification_update.reference)

    if int(notification_update.page_count) != notification.billable_units:
        msg = 'Notification with id {} has {} billable_units but DVLA says page count is {}'.format(
            notification.id, notification.billable_units, notification_update.page_count
        )
        try:
            raise DVLAException(msg)
        except DVLAException:
            current_app.logger.exception(msg)


@notify_celery.task(name='process-incomplete-jobs')
@statsd(namespace='tasks')
def process_incomplete_jobs(job_ids):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JOB_STATUS_IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    current_app.logger.info('Resuming Job(s) %s', job_ids)
    for job_id in job_ids:
        process_incomplete_job(job_id)


def process_incomplete_job(job_id):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info('Resuming job %s from row %s', job_id, resume_from_row)

    db_template = dao_get_template_by_id(job.template_id, job.template_version)

    TemplateClass = get_template_class(db_template.template_type)
    template = TemplateClass(db_template.__dict__)

    for row in RecipientCSV(
        s3.get_job_from_s3(str(job.service_id), str(job.id)),
        template_type=template.template_type,
        placeholders=template.placeholder_names,
    ).get_rows():
        if row.index > resume_from_row:
            process_row(row, template, job, job.service)

    job_complete(job, resumed=True)
