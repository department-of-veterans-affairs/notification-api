from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import and_, select

from app import db, notify_celery, twilio_sms_client
from app.celery.exceptions import NonRetryableException
from app.constants import NOTIFICATION_STATUS_TYPES_COMPLETED
from app.models import Notification

from notifications_utils.statsd_decorators import statsd


def _get_notifications() -> list:
    """Returns a list of notifications not in final state."""

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = (
        select(Notification.id, Notification.status, Notification.reference)
        .where(
            and_(
                Notification.notification_type == 'sms',
                Notification.created_at < one_hour_ago,
                ~Notification.status.in_(NOTIFICATION_STATUS_TYPES_COMPLETED),
                Notification.sent_by == 'twilio',
            )
        )
        .limit(current_app.config['TWILIO_STATUS_PAGE_SIZE'])
    )
    return db.session.execute(stmt).all()


@notify_celery.task(name='update-twilio-status')
@statsd(namespace='tasks')
def update_twilio_status():
    """Update the status of notifications sent via Twilio. This task is scheduled to run every 5 minutes. It fetches
    notifications that are not in a final state, limited to the config setting TWILIO_STATUS_PAGE_SIZE, and updates
    their status using the app's Twilio client.
    """
    notifications = _get_notifications()
    current_app.logger.info('[TWILIO_STATUS_TASK] Processing %s notifications for status updates', len(notifications))

    if not notifications:
        return

    updated_count = 0
    for notification in notifications:
        try:
            twilio_sms_client.update_notification_status_override(notification.reference)
            updated_count += 1
        except NonRetryableException as e:
            current_app.logger.error(
                '[TWILIO_STATUS_TASK] Failed to update notification %s: %s due to rate limit, aborting.',
                str(notification.id),
                str(e),
            )
            break

    current_app.logger.info(
        '[TWILIO_STATUS_TASK] Completed. Updated %s/%s notifications', updated_count, len(notifications)
    )
