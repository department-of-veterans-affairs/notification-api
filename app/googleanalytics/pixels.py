import os
from urllib.parse import urlencode

from flask import current_app


def build_ga_pixel_url(
    notification,
    provider,
):
    url_params_dict = {
        'v': '1',
        't': 'event',
        'tid': current_app.config['GOOGLE_ANALYTICS_TID'],
        'cid': notification.id,
        'aip': '1',
        'ec': 'email',
        'ea': 'open',
        'el': notification.template.name,
        'dp': f"/email/vanotify"
        f"{'/' + notification.service.organisation.name if notification.service.organisation else ''}"
        f"/{notification.service.name}"
        f"/{notification.template.name}",
        'dt': notification.subject,
        'cn': notification.template.name,
        'cs': provider.get_name(),
        'cm': 'email',
        'ci': notification.template.id,
    }

    url_str = current_app.config['GOOGLE_ANALYTICS_URL']
    url_params = urlencode(url_params_dict)
    url = f'{url_str}?{url_params}'

    current_app.logger.info(f'Generated google analytics pixel URL: {url}')
    return url


def build_ga4_open_email_event(notification, provider):
    
    url_params_dict = {'measurement_id': os.environ['GOOGLE_ANALYTICS_MEASUREMENT_ID'],
                       'api_secret': os.environ['GOOGLE_ANALYTICS_API_SECRET'],

    }
    
    data = {
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

    url_str = current_app.config['GOOGLE_ANALYTICS_GA4_URL']
    # https://www.google-analytics.com/mp/
    url_params = urlencode(url_params_dict)
    url = f'{url_str}?{url_params}'

    return [url, data]