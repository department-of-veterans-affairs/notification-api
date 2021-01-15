from app.dao.provider_details_dao import get_provider_details_by_id
from app.errors import InvalidRequest
from app.models import EMAIL_TYPE, SMS_TYPE


def validate_service_providers(update_request: dict):
    email_provider_id = update_request.get('email_provider_id')
    if not(email_provider_id is None or is_provider_valid(email_provider_id, EMAIL_TYPE)):
        throw_invalid_request_error('email')

    sms_provider_id = update_request.get('sms_provider_id')
    if not(sms_provider_id is None or is_provider_valid(sms_provider_id, SMS_TYPE)):
        throw_invalid_request_error('sms')


def is_provider_valid(provider_id: str, notification_type: str) -> bool:
    provider_details = get_provider_details_by_id(provider_id)
    return (
        provider_details is not None
        and provider_details.active
        and provider_details.notification_type == notification_type
    )


def validate_template_providers(request: dict):
    provider_id = request.get('provider_id')
    template_type = request.get('template_type')

    if not(provider_id is None or is_provider_valid(provider_id, template_type)):
        throw_invalid_request_error(template_type)


def validate_template_provider(provider_id: str, template_type: str):
    if not(provider_id is None or is_provider_valid(provider_id, template_type)):
        throw_invalid_request_error(template_type)


def throw_invalid_request_error(template_type):
    raise InvalidRequest(f'invalid {template_type}_provider_id', status_code=400)
