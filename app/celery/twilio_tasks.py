from flask import current_app
from sqlalchemy import select

from app import db, notify_celery, twilio_sms_client
from app.models import Notification


TWILIO_STATUS_PAGE_SIZE = 5

def _get_notifications()->list:
    """
    Returns a list of notifications not in final state, limited to 500
    """
    query = select([Notification]).where(Notification.status != 'delivered').limit(TWILIO_STATUS_PAGE_SIZE)
    return db.session.execute(query).all()



@notify_celery.task(bind=True, name='update-twilio-status')
def update_twilio_status():
    """
    Update the status of notifications sent via Twilio
    """
    notifications = _get_notifications()
    for notification in notifications:
        current_app.logger.info("Updating status for notification %s", notification.id)

        # The twilio message sid is in the 'reference' field
        message_sid = notification.reference
        twilio_message = twilio_sms_client.get_twilio_message(message_sid)

        if twilio_message:
            notification.status = twilio_message.status
            current_app.logger.info("Updated status for notification %s to %s", notification.id, notification.status)

    return len(notifications)