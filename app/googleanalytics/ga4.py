import os
from urllib.parse import urlencode
from flask import current_app

def build_ga4_open_email_event_url(notification, provider):
    
    url_params_dict = {
        'measurement_id': os.environ['GOOGLE_ANALYTICS_MEASUREMENT_ID'],
        'api_secret': os.environ['GOOGLE_ANALYTICS_API_SECRET'],

    }

    url_str = current_app.config['GOOGLE_ANALYTICS_GA4_URL']
    # https://www.google-analytics.com/mp/
    url_params = urlencode(url_params_dict)
    url = f'{url_str}?{url_params}'

    return url

def build_ga4_open_email_event_body(notification, provider):
    
    return {
        "events": [{
            "name": "open_email",
            "params": {
                "campaign_id": notification.template.name,
                "campaign": notification.template.id,
                "source": "vanotify",
                "medium": "email",
            }
        }]
    }