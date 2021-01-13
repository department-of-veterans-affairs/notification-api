import uuid

from app.dao.provider_details_dao import get_provider_details_by_id
from app.dao.services_dao import dao_update_service
from app.models import Service


def update_service(service: Service):

    # check if a provider is added or updated for teh services
    dao_update_service(service)


def is_provider_valid(provider_id: uuid, notification_type: str) -> bool:
    # check if provider exists
    provider_details_array = get_provider_details_by_id(provider_id)
    return (
        provider_details_array is not None
        and provider_details_array[0].active
        and provider_details_array[0].notification_type == notification_type
    )
