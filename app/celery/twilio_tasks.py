from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import select

from app import db, notify_celery, twilio_sms_client
from app.config import TWILIO_STATUS_PAGE_SIZE
from app.constants import NOTIFICATION_STATUS_TYPES_COMPLETED
from app.models import Notification


def _get_notifications() -> list:
    """
    Returns a list of notifications not in final state
    """
    current_app.logger.info('Getting notifications to update status')
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    query = (
        select([Notification])
        .where(Notification.notification_type == 'sms')
        .where(Notification.sent_by == 'twilio')
        .where(~Notification.status.in_(NOTIFICATION_STATUS_TYPES_COMPLETED))
        .where(Notification.created_at > one_hour_ago)
        .limit(TWILIO_STATUS_PAGE_SIZE)
    )
    current_app.logger.debug('Query: %s', query)
    return db.session.execute(query).scalars().all()


@notify_celery.task(name='update-twilio-status')
def update_twilio_status():
    """
    Update the status of notifications sent via Twilio
    """
    notifications = _get_notifications()
    for notification in notifications:
        current_app.logger.info('Updating status for notification %s', notification.id)

        # The twilio message sid is in the 'reference' field
        message_sid = notification.reference
        twilio_sms_client.update_notification_status_override(message_sid)
