import os
from flask import current_app
from urllib.parse import quote

TEST_DOMAIN = 'https://test-api.va.gov/vanotify/'
DEV_DOMAIN = 'https://dev-api.va.gov/vanotify/'
PERF_DOMAIN = 'https://sandbox-api.va.gov/vanotify/'
STAGING_DOMAIN = 'https://staging-api.va.gov/vanotify/'
PROD_DOMAIN = 'https://api.va.gov/vanotify/'

NOTIFICATION_API_GA4_GET_ENDPOINT = 'ga4/open-email-tracking'

GA4_PIXEL_TRACKING_NAME = 'email_open'
GA4_PIXEL_TRACKING_SOURCE = 'vanotify'
GA4_PIXEL_TRACKING_MEDIUM = 'email'

def get_domain_for_environment():
    environment = os.getenv('NOTIFY_ENVIRONMENT', 'development')

    ENVIRONMENT_DOMAINS = {
        'test': TEST_DOMAIN,
        'development': DEV_DOMAIN,
        'perf': PERF_DOMAIN,
        'staging': STAGING_DOMAIN,
        'prod': PROD_DOMAIN,
    }

    return ENVIRONMENT_DOMAINS[environment]

def build_dynamic_ga4_pixel_tracking_url(notification):
    """
    Constructs a dynamic URL that contains information on the notification email being sent.
    The dynamic URL is used for pixel tracking and sends a request to our application when
    email is opened.

    :param notification: The notification object containing template and service details.
    :return: A dynamically constructed URL string.
    """

    domain = get_domain_for_environment()
    ga4_url = NOTIFICATION_API_GA4_GET_ENDPOINT
    url = (
        f'{domain}'
        f'{ga4_url}?'
        f'campaign={quote(notification.template.name)}&campaign_id={quote(str(notification.template.id))}&'
        f'name={quote(GA4_PIXEL_TRACKING_NAME)}&source={quote(GA4_PIXEL_TRACKING_SOURCE)}&medium={quote(GA4_PIXEL_TRACKING_MEDIUM)}&'
        f'content={quote(notification.service.name)}/{quote(str(notification.service.id))}/{quote(str(notification.id))}'
    )

    current_app.logger.info(f'Generated Google Analytics 4 pixel URL: {url}')
    return url
