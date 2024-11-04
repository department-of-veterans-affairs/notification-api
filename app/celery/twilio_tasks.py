from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import select

from app import db, notify_celery, twilio_sms_client
from app.constants import NOTIFICATION_STATUS_TYPES_COMPLETED
from app.models import Notification


def _get_notifications() -> list:
    """Returns a list of notifications not in final state."""

    current_app.logger.info('Getting notifications to update status')
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    query = (
        select([Notification])
        .where(Notification.notification_type == 'sms')
        .where(Notification.sent_by == 'twilio')
        .where(~Notification.status.in_(NOTIFICATION_STATUS_TYPES_COMPLETED))
        .where(Notification.created_at > one_hour_ago)
        .limit(current_app.config['TWILIO_STATUS_PAGE_SIZE'])
    )
    return db.session.execute(query).scalars().all()


@notify_celery.task(name='update-twilio-status')
def update_twilio_status():
    """Update the status of notifications sent via Twilio. This task is scheduled to run every 5 minutes. It fetches
    notifications that are not in a final state, limited to the config setting TWILIO_STATUS_PAGE_SIZE, and updates
    their status using the app's Twilio client.
    """
    notifications = _get_notifications()
    current_app.logger.info('Found %s notifications to update', len(notifications))
    for notification in notifications:
        # The twilio message sid is in the 'reference' field
        message_sid = notification.reference
        twilio_sms_client.update_notification_status_override(message_sid)
