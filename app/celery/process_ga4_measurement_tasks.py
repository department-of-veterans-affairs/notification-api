from urllib.parse import urlencode

import requests

from flask import current_app

from app import notify_celery
from app.celery.exceptions import AutoRetryException


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
def post_to_ga4(
    notification_id: str,
    template_name: str,
    template_id: str,
    service_id: str,
    service_name: str,
    client_id='vanotify',
    name='open_email',
    source='vanotify',
    medium='email',
) -> bool:
    """
    This celery task is used to post to Google Analytics 4. It is exercised when a veteran opens an e-mail.

    :param notification_id: The notification ID. Shows up in GA4 as part of the event content.
    :param template_name: The template name. Shows up in GA4 as the campaign.
    :param template_id: The template ID. Shows up in GA4 as the campaign ID.
    :param service_id: The service ID. Shows up in GA4 as part of the event content.
    :param service_name: The service name. Shows up in GA4 as part of the event content.
    :param client_id: The client ID. Shows up in GA4 as the client ID.
    :param name: The event name. Shows up in GA4 as the event name.
    :param source: The event source. Shows up in GA4 as the event source.
    :param medium: The event medium. Shows up in GA4 as the event medium.

    :return: True if the post was successful, False otherwise.
    """
    current_app.logger.info('Posting to GA4: notification_id %s', notification_id)

    ga_api_secret, ga_measurement_id = get_ga4_config()
    if not ga_api_secret:
        raise AutoRetryException('GA4_API_SECRET is not set')
    if not ga_measurement_id:
        raise AutoRetryException('GA4_MEASUREMENT_ID is not set')

    url_str = current_app.config.get('GA4_URL', '')
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

    return response.status_code == 204
