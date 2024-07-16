from urllib.parse import urlencode

from flask import current_app
import requests

from app import notify_celery
from app.celery.exceptions import AutoRetryException


@notify_celery.task(
    bind=True,
    name='post_ga4',
    throws=(AutoRetryException,),
    autoretry_for=(AutoRetryException,),
    max_retries=2886,
    retry_backoff=True,
    retry_backoff_max=60,
)
def post_to_ga4(notification_id, template_name, template_id, service_id, service_name):
    ga_api_secret = current_app.config['GOOGLE_ANALYTICS_API_SECRET']
    ga_measurement_id = current_app.config['GOOGLE_ANALYTICS_MEASUREMENT_ID']
    url_str = current_app.config['GOOGLE_ANALYTICS_GA4_URL']
    url_params_dict = {
        'measurement_id': ga_measurement_id,
        'api_secret': ga_api_secret,
    }
    url_params = urlencode(url_params_dict)
    url = f'{url_str}?{url_params}'

    content = f'{service_name}/{service_id}/{notification_id}'

    event_body = {
        'events': [
            {
                'name': 'open_email',
                'params': {
                    'campaign_id': template_id,
                    'campaign': template_name,
                    'source': 'vanotify',
                    'medium': 'email',
                    'content': content,
                },
            }
        ]
    }
    headers = {
        'Content-Type': 'application/json',
    }
    response = requests.post(url, headers=headers, json=event_body, timeout=1)
    return response.status_code, response.json()
