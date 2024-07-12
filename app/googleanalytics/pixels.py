import os

from flask import current_app


TEST_DOMAIN = 'https://test-api.va.gov/notify/'
DEV_DOMAIN = 'https://dev-api.va.gov/notify/'
PERF_DOMAIN = 'https://sandbox-api.va.gov/notify/'
STAGING_DOMAIN = 'https://staging-api.va.gov/notify/'
PROD_DOMAIN = 'https://api.va.gov/notify/'

NOTIFICATION_API_GA4_GET_ENDPOINT = 'ga4/open-email-tracking'


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
    The dynamic URL is used to for pixel tracking and sends a request to our application when
    email is opened.

    :param notification: The notification object containing template and service details.
    :return: A dynamically constructed URL string.
    """

    domain = get_domain_for_environment()
    ga4_url = NOTIFICATION_API_GA4_GET_ENDPOINT
    url = (
        f'{domain}'
        f'{ga4_url}?'
        f'campaign={notification.template.name}&campaign_id={notification.template.id}&'
        f'name=email_opens&source=vanotify&medium=email&'
        f'content={notification.service.name}/{notification.service.id}/{notification.id}'
    )

    current_app.logger.info(f'Generated Google Analytics 4 pixel URL: {url}')
    return url
