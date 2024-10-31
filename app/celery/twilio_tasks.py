from flask import current_app
from sqlalchemy import select

from app import db, notify_celery, twilio_sms_client
from app.constants import NOTIFICATION_STATUS_TYPES_COMPLETED
from app.models import Notification


TWILIO_STATUS_PAGE_SIZE = 5


def _get_notifications() -> list:
    """
    Returns a list of notifications not in final state
    """
    current_app.logger.info('Getting notifications to update status')
    # query = select([Notification]).where(Notification.status != 'delivered').limit(TWILIO_STATUS_PAGE_SIZE)
    query = (
        select([Notification])
        .where(Notification.status.in_(NOTIFICATION_STATUS_TYPES_COMPLETED))
        .limit(TWILIO_STATUS_PAGE_SIZE)
    )
    current_app.logger.debug('Query: %s', query)
    return db.session.execute(query).all()


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
