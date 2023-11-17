from . import return_json_from_response, validate_v0, validate
from app.models import ApiKey, KEY_TYPE_NORMAL
from app.dao.api_key_dao import save_model_api_key
from app.v2.notifications.notification_schemas import get_notification_response, get_notifications_response
from tests import create_authorization_header


def _get_notification(client, notification, url, api_key):
    save_model_api_key(ApiKey(
        service=notification.service,
        name='api_key',
        created_by=notification.service.created_by,
        key_type=KEY_TYPE_NORMAL
    ))
    auth_header = create_authorization_header(api_key)
    return client.get(url, headers=[auth_header])


# v2

def test_get_v2_sms_contract(client, sample_api_key, sample_notification):
    api_key = sample_api_key()
    notification = sample_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/v2/notifications/{}'.format(notification.id), api_key
    ))
    validate(response_json, get_notification_response)


def test_get_v2_email_contract(client, sample_api_key, sample_email_notification):
    api_key = sample_api_key()
    notification = sample_email_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/v2/notifications/{}'.format(notification.id), api_key
    ))
    validate(response_json, get_notification_response)


def test_get_v2_notifications_contract(client, sample_api_key, sample_notification):
    api_key = sample_api_key()
    notification = sample_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/v2/notifications', api_key
    ))
    validate(response_json, get_notifications_response)


# v0

def test_get_api_sms_contract(client, sample_api_key, sample_notification):
    api_key = sample_api_key()
    notification = sample_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/notifications/{}'.format(notification.id), api_key
    ))
    validate_v0(response_json, 'GET_notification_return_sms.json')


def test_get_api_email_contract(client, sample_api_key, sample_email_notification):
    api_key = sample_api_key()
    notification = sample_email_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/notifications/{}'.format(notification.id), api_key
    ))
    validate_v0(response_json, 'GET_notification_return_email.json')


def test_get_job_sms_contract(client, sample_api_key, sample_notification):
    api_key = sample_api_key()
    notification = sample_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/notifications/{}'.format(notification.id), api_key
    ))
    validate_v0(response_json, 'GET_notification_return_sms.json')


def test_get_job_email_contract(client, sample_api_key, sample_email_notification):
    api_key = sample_api_key()
    notification = sample_email_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/notifications/{}'.format(notification.id), api_key
    ))
    validate_v0(response_json, 'GET_notification_return_email.json')


def test_get_notifications_contract(client, sample_api_key, sample_notification, sample_email_notification):
    api_key = sample_api_key()
    notification = sample_notification(service=api_key.service)
    response_json = return_json_from_response(_get_notification(
        client, notification, '/notifications', api_key
    ))
    validate_v0(response_json, 'GET_notifications_return.json')
