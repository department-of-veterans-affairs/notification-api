from dataclasses import dataclass
from datetime import datetime

from cachetools import TTLCache, cached
from sqlalchemy import select

from app import db
from app.constants import COMPLAINT_CALLBACK_TYPE, DELIVERY_STATUS_CALLBACK_TYPE, INBOUND_SMS_CALLBACK_TYPE
from app.dao.dao_utils import transactional, version_class
from app.models import ServiceCallback
from app.utils import create_uuid


@transactional
@version_class(ServiceCallback)
def save_service_callback_api(service_callback_api):
    service_callback_api.id = create_uuid()
    service_callback_api.created_at = datetime.utcnow()
    db.session.add(service_callback_api)


@transactional
@version_class(ServiceCallback)
def reset_service_callback_api(
    service_callback_api,
    updated_by_id,
    url=None,
    bearer_token=None,
):
    if url:
        service_callback_api.url = url
    if bearer_token:
        service_callback_api.bearer_token = bearer_token
    service_callback_api.updated_by_id = updated_by_id
    service_callback_api.updated_at = datetime.utcnow()

    db.session.add(service_callback_api)


@transactional
@version_class(ServiceCallback)
def store_service_callback_api(service_callback_api):
    service_callback_api.updated_at = datetime.utcnow()
    db.session.add(service_callback_api)


def get_service_callbacks(service_id):
    stmt = select(ServiceCallback).where(ServiceCallback.service_id == service_id)
    return db.session.scalars(stmt).all()


###
# Not to be used in rest controllers where we need to operate within a service user has permissions for
###
def get_service_callback(service_callback_id):
    return db.session.get(ServiceCallback, service_callback_id)


def query_service_callback(
    service_id,
    service_callback_id,
):
    stmt = select(ServiceCallback).where(
        ServiceCallback.service_id == service_id, ServiceCallback.id == service_callback_id
    )
    return db.session.scalars(stmt).one()


@dataclass
class DeliveryStatusCallbackApiData:
    id: str
    url: str
    bearer_token: str
    include_provider_payload: bool
    callback_type: str | None


@cached(cache=TTLCache(maxsize=1024, ttl=600))
def get_service_delivery_status_callback_api_for_service(
    service_id,
    notification_status,
) -> DeliveryStatusCallbackApiData | None:
    stmt = select(ServiceCallback).where(
        ServiceCallback.notification_statuses.contains([notification_status]),
        ServiceCallback.service_id == service_id,
        ServiceCallback.callback_type == DELIVERY_STATUS_CALLBACK_TYPE,
    )

    service_callback = db.session.scalars(stmt).first()

    if service_callback is None:
        return None

    return DeliveryStatusCallbackApiData(
        id=str(service_callback.id),
        url=service_callback.url,
        bearer_token=service_callback.bearer_token,
        include_provider_payload=service_callback.include_provider_payload,
        callback_type=service_callback.callback_type,
    )


def get_service_complaint_callback_api_for_service(service_id):
    stmt = select(ServiceCallback).where(
        ServiceCallback.service_id == service_id, ServiceCallback.callback_type == COMPLAINT_CALLBACK_TYPE
    )

    return db.session.scalars(stmt).first()


def get_service_inbound_sms_callback_api_for_service(service_id):
    stmt = select(ServiceCallback).where(
        ServiceCallback.service_id == service_id, ServiceCallback.callback_type == INBOUND_SMS_CALLBACK_TYPE
    )

    return db.session.scalars(stmt).first()


@transactional
def delete_service_callback_api(service_callback_api):
    db.session.delete(service_callback_api)
