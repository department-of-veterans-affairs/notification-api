import uuid

from app.dao.provider_details_dao import get_provider_details_by_id
from app.dao.services_dao import dao_create_service
from app.errors import InvalidRequest
from app.models import Service, User, EMAIL_TYPE, SMS_TYPE


def create_service(service: Service, user: User):
    # validate any provider that the service points to
    if not(service.email_provider_id is None or is_provider_valid(service.email_provider_id, EMAIL_TYPE)):
        raise InvalidRequest('invalid email_provider_id', status_code=400)

    if not(service.sms_provider_id is None or is_provider_valid(service.sms_provider_id, SMS_TYPE)):
        raise InvalidRequest('invalid sms_provider_id', status_code=400)

    dao_create_service(service, user)


def is_provider_valid(provider_id: uuid, notification_type: str) -> bool:
    # check if provider exists
    provider_details_array = get_provider_details_by_id(provider_id)
    return (
        provider_details_array is not None
        and provider_details_array[0].active
        and provider_details_array[0].notification_type == notification_type
    )
