import os
from urllib.parse import urlencode

from flask import current_app
import requests
from requests.exceptions import RequestException

# code from first iternation
# def build_ga4_open_email_event_url(notification, provider):
    
#     url_params_dict = {
#         'measurement_id': os.environ['GOOGLE_ANALYTICS_MEASUREMENT_ID'],
#         'api_secret': os.environ['GOOGLE_ANALYTICS_API_SECRET'],

#     }

#     url_str = current_app.config['GOOGLE_ANALYTICS_GA4_URL']
#     # https://www.google-analytics.com/mp/
#     url_params = urlencode(url_params_dict)
#     url = f'{url_str}?{url_params}'

#     return url

# def build_ga4_open_email_event_body(notification, provider):
    
#     return {
#         "events": [{
#             "name": "open_email",
#             "params": {
#                 "campaign_id": notification.template.name,
#                 "campaign": notification.template.id,
#                 "source": "vanotify",
#                 "medium": "email",
#             }
#         }]
#     }


def send_ga4_open_email_event(notification, provider):
    try:
        # Build URL
        url_params_dict = {
            'measurement_id': os.environ['GOOGLE_ANALYTICS_MEASUREMENT_ID'],
            'api_secret': os.environ['GOOGLE_ANALYTICS_API_SECRET'],
        }
        url_str = current_app.config['GOOGLE_ANALYTICS_GA4_URL']
        url_params = urlencode(url_params_dict)
        url = f'{url_str}?{url_params}'

        content = f"template_id={notification.template.id}/service_id={notification.service.id}/service_name={notification.service.name}"

        event_body = {
            "events": [{
                "name": "open_email",
                "params": {
                    "campaign_id": notification.template.id,
                    "campaign": notification.template.name,
                    "source": "vanotify",
                    "medium": "email",
                    "content": content,
                }
            }]
        }

        response = requests.post(url, json=event_body)

        return response

    except RequestException as error:
        current_app.logger.error('Error sending GA4 event: %s', error)
        return None
