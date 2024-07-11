from urllib.parse import urlencode
import requests
from flask import current_app
from celery import Celery

# Initialize Celery
celery = Celery(__name__)


@celery.task
def post_to_ga4(notification_id, template_name, template_id, service_id, service_name):
    # Build URL
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

    response = requests.post(url, json=event_body, timeout=3)
    return response.status_code, response.json()
