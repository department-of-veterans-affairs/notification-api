import uuid
from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.letter_timings import letter_can_be_cancelled, CANCELLABLE_JOB_LETTER_STATUSES
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import (
    asc,
    desc,
    func,
    select,
    update,
)

from app import db
from app.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FINISHED,
    JOB_STATUS_PENDING,
    JOB_STATUS_SCHEDULED,
    LETTER_TYPE,
    NOTIFICATION_CANCELLED,
    NOTIFICATION_CREATED,
)
from app.dao.dao_utils import transactional
from app.dao.templates_dao import dao_get_template_by_id
from app.utils import midnight_n_days_ago

from app.models import (
    Job,
    Notification,
    Template,
    ServiceDataRetention,
)


@statsd(namespace='dao')
def dao_get_notification_outcomes_for_job(
    service_id,
    job_id,
):
    stmt = (
        select(func.count(Notification.status).label('count'), Notification.status)
        .where(Notification.service_id == service_id, Notification.job_id == job_id)
        .group_by(Notification.status)
    )

    return db.session.execute(stmt).all()


def dao_get_job_by_service_id_and_job_id(
    service_id,
    job_id,
):
    return db.session.scalars(select(Job).where(Job.service_id == service_id, Job.id == job_id)).one()


def dao_get_jobs_by_service_id(
    service_id,
    limit_days=None,
    page=1,
    page_size=50,
    statuses=None,
):
    query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config['TEST_MESSAGE_FILENAME'],
        Job.original_file_name != current_app.config['ONE_OFF_MESSAGE_FILENAME'],
    ]
    if limit_days is not None:
        query_filter.append(Job.created_at >= midnight_n_days_ago(limit_days))
    if statuses is not None and statuses != ['']:
        query_filter.append(Job.job_status.in_(statuses))

    stmt = select(Job).where(*query_filter).order_by(Job.processing_started.desc(), Job.created_at.desc())
    return db.paginate(stmt, page=page, per_page=page_size)


def dao_get_job_by_id(job_id):
    return db.session.scalars(select(Job).where(Job.id == job_id)).one()


def dao_archive_job(job):
    job.archived = True
    db.session.add(job)
    db.session.commit()


def dao_set_scheduled_jobs_to_pending():
    """
    Sets all past scheduled jobs to pending, and then returns them for further processing.

    this is used in the run_scheduled_jobs task, so we put a FOR UPDATE lock on the job table for the duration of
    the transaction so that if the task is run more than once concurrently, one task will block the other select
    from completing until it commits.
    """

    stmt = (
        select(Job)
        .where(Job.job_status == JOB_STATUS_SCHEDULED, Job.scheduled_for < datetime.utcnow())
        .order_by(asc(Job.scheduled_for))
        .with_for_update()
    )

    jobs = db.session.scalars(stmt).all()

    for job in jobs:
        job.job_status = JOB_STATUS_PENDING

    db.session.add_all(jobs)
    db.session.commit()

    return jobs


def dao_get_future_scheduled_job_by_id_and_service_id(
    job_id,
    service_id,
):
    stmt = select(Job).where(
        Job.service_id == service_id,
        Job.id == job_id,
        Job.job_status == JOB_STATUS_SCHEDULED,
        Job.scheduled_for > datetime.utcnow(),
    )
    return db.session.scalars(stmt).one()


def dao_create_job(job):
    if not job.id:
        job.id = uuid.uuid4()
    db.session.add(job)
    db.session.commit()


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def dao_get_jobs_older_than_data_retention(notification_types):
    stmt = select(ServiceDataRetention).where(ServiceDataRetention.notification_type.in_(notification_types))
    flexible_data_retention = db.session.scalars(stmt).all()

    jobs = []
    today = datetime.utcnow().date()
    for f in flexible_data_retention:
        end_date = today - timedelta(days=f.days_of_retention)

        stmt = (
            select(Job)
            .join(Template)
            .where(
                func.coalesce(Job.scheduled_for, Job.created_at) < end_date,
                Job.archived.is_(False),
                Template.template_type == f.notification_type,
                Job.service_id == f.service_id,
            )
            .order_by(desc(Job.created_at))
        )

        jobs.extend(db.session.scalars(stmt).all())

    end_date = today - timedelta(days=7)
    for notification_type in notification_types:
        services_with_data_retention = [
            x.service_id for x in flexible_data_retention if x.notification_type == notification_type
        ]

        stmt = (
            select(Job)
            .join(Template)
            .where(
                func.coalesce(Job.scheduled_for, Job.created_at) < end_date,
                Job.archived.is_(False),
                Template.template_type == notification_type,
                Job.service_id.notin_(services_with_data_retention),
            )
            .order_by(desc(Job.created_at))
        )

        jobs.extend(db.session.scalars(stmt).all())

    return jobs


@transactional
def dao_cancel_letter_job(job):
    stmt = (
        update(Notification)
        .where(Notification.job_id == job.id)
        .values(
            status=NOTIFICATION_CANCELLED,
            updated_at=datetime.utcnow(),
            billable_units=0,
        )
    )
    cancelled_count = db.session.execute(stmt).rowcount

    job.job_status = JOB_STATUS_CANCELLED
    dao_update_job(job)
    return cancelled_count


def can_letter_job_be_cancelled(job):
    template = dao_get_template_by_id(job.template_id)
    if template.template_type != LETTER_TYPE:
        return False, 'Only letter jobs can be cancelled through this endpoint. This is not a letter job.'

    notifications = db.session.scalars(select(Notification).where(Notification.job_id == job.id)).all()

    if job.job_status != JOB_STATUS_FINISHED or len(notifications) != job.notification_count:
        return False, 'We are still processing these letters, please try again in a minute.'
    count_cancellable_notifications = len([n for n in notifications if n.status in CANCELLABLE_JOB_LETTER_STATUSES])
    if count_cancellable_notifications != job.notification_count or not letter_can_be_cancelled(
        NOTIFICATION_CREATED, job.created_at
    ):
        return False, 'It’s too late to cancel sending, these letters have already been sent.'

    return True, None
