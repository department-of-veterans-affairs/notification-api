from urllib.parse import urlencode

import requests

from flask import current_app

from app import notify_celery
from app.celery.exceptions import AutoRetryException


@notify_celery.task(
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=True,
    retry_backoff_max=60,
)
def post_to_ga4(
    notification_id,
    template_name,
    template_id,
    service_id,
    service_name,
    client_id='vanotify',
    name='open_email',
    source='vanotify',
    medium='email',
):
    """
    This celery task is used to post to Google Analytics 4. It is exercised when a veteran opens an e-mail.

    :param notification_id: The notification ID.
    :param template_name: The template name.
    :param template_id: The template ID.
    :param service_id: The service ID.
    :param service_name: The service name.
    :param client_id: The client ID.
    :param name: The event name.
    :param source: The event source.
    :param medium: The event medium.

    :return: The status code and the response JSON.
    """
    current_app.logger.info('Posting to GA4: notification_id %s', notification_id)
    try:
        ga_api_secret = current_app.config['GA4_API_SECRET']
        ga_measurement_id = current_app.config['GA4_MEASUREMENT_ID']
        url_str = current_app.config['GA4_URL']
    except KeyError as e:
        current_app.logger.error('Configuration error: %s', e)
        raise AutoRetryException(f'Configuration error: {e}')

    url_params_dict = {
        'measurement_id': ga_measurement_id,
        'api_secret': ga_api_secret,
    }
    url_params = urlencode(url_params_dict)
    url_str = current_app.config['GA4_URL']
    url = f'{url_str}?{url_params}'
    content = f'{service_name}/{service_id}/{notification_id}'

    event_body = {
        'client_id': client_id,
        'events': [
            {
                'name': name,
                'params': {
                    'campaign_id': str(template_id),
                    'campaign': str(template_name),
                    'source': source,
                    'medium': medium,
                    'content': str(content),
                },
            }
        ],
    }
    headers = {
        'Content-Type': 'application/json',
    }
    current_app.logger.debug('Posting to GA4: %s', event_body)
    response = requests.post(url, json=event_body, headers=headers, timeout=1)
    current_app.logger.debug('GA4 response: %s', response.status_code)
    response.raise_for_status()

    return True
