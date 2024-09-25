from urllib.parse import urlencode

import requests

from flask import current_app
from sqlalchemy import select

from app import db, notify_celery
from app.celery.exceptions import AutoRetryException
from app.models import Notification


def get_ga4_config() -> tuple:
    """
    Get the Google Analytics 4 configuration.

    :return: A tuple containing the GA4 API secret and the GA4 measurement ID.
    """
    ga_api_secret = current_app.config.get('GA4_API_SECRET', '')
    ga_measurement_id = current_app.config.get('GA4_MEASUREMENT_ID', '')

    return ga_api_secret, ga_measurement_id


@notify_celery.task(
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=True,
    retry_backoff_max=60,
)
def post_to_ga4(notification_id: str, event_name, event_source, event_medium) -> bool:
    """
    This celery task is used to post to Google Analytics 4. It is exercised when a veteran opens an e-mail.

    :param notification_id: The notification ID. Shows up in GA4 as part of the event content.

    :return: True if the post was successful, False otherwise.
    """
    # Log the incoming parameters.
    current_app.logger.info(
        'GA4: post_to_ga4: notification_id: %s, event_name: %s, event_source: %s, event_medium: %s',
        notification_id,
        event_name,
        event_source,
        event_medium,
    )

    ga_api_secret, ga_measurement_id = get_ga4_config()
    if not ga_api_secret:
        current_app.logger.error('GA4_API_SECRET is not set')
        return False

    if not ga_measurement_id:
        current_app.logger.error('GA4_MEASUREMENT_ID is not set')
        return False

    # Retrieve the notification from the database
    stmt = select(Notification).where(Notification.id == notification_id)
    notification = db.session.scalars(stmt).first()
    if not notification:
        current_app.logger.error('Notification %s not found', notification_id)
        return False

    template_name = notification.template.name
    template_id = notification.template.id
    service_id = notification.service_id
    service_name = notification.service.name

    url_str = current_app.config.get('GA4_URL', '')
    url_params_dict = {
        'measurement_id': ga_measurement_id,
        'api_secret': ga_api_secret,
    }
    url_params = urlencode(url_params_dict)
    url_str = current_app.config['GA4_URL']
    url = f'{url_str}?{url_params}'

    event_body = {
        'client_id': event_source,
        'events': [
            {
                'name': event_name,
                'params': {
                    'campaign_id': str(template_id),
                    'campaign': str(template_name),
                    'source': event_source,
                    'medium': event_medium,
                    'service_id': str(service_id),
                    'service_name': service_name,
                    'notification_id': notification_id,
                },
            }
        ],
    }
    headers = {
        'Content-Type': 'application/json',
    }
    current_app.logger.debug('Posting to GA4 url: %s with payload %s', url_str, event_body)

    status = False
    try:
        current_app.logger.info('Posting event to GA4: %s', event_name)
        response = requests.post(url, json=event_body, headers=headers, timeout=1)
        current_app.logger.debug('GA4 response: %s', response.status_code)
        response.raise_for_status()
        status = response.status_code == 204
    except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as e:
        current_app.logger.exception(e)
        raise AutoRetryException from e
    else:
        current_app.logger.info('GA4 event %s posted successfully', event_name)
    return status
