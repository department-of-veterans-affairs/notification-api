import requests
from flask import current_app

from app.constants import HTTP_TIMEOUT


def confirm_subscription(confirmation_request):
    url = confirmation_request.get('SubscribeURL')
    if not url:
        current_app.logger.warning('SubscribeURL does not exist or empty.')
        return

    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        current_app.logger.exception('Response: %s', response.text)
        raise

    return confirmation_request['TopicArn']


def autoconfirm_subscription(req_json):
    if req_json.get('Type') == 'SubscriptionConfirmation':
        current_app.logger.debug('SNS subscription confirmation url: %s', req_json['SubscribeURL'])
        subscribed_topic = confirm_subscription(req_json)
        return subscribed_topic
