from cachetools import TTLCache, cached
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, select, update

from app import db
from app.dao.dao_utils import transactional
from app.models import ProviderDetails, ServiceSmsSender, InboundNumber, ServiceSmsSenderData, DATETIME_FORMAT
from app.service.exceptions import (
    SmsSenderDefaultValidationException,
    SmsSenderProviderValidationException,
    SmsSenderInboundNumberIntegrityException,
    SmsSenderRateLimitIntegrityException,
)

sms_sender_data_cache = TTLCache(maxsize=1024, ttl=timedelta(hours=12), timer=datetime.now)


def insert_service_sms_sender(
    service,
    sms_sender,
):
    """
    This method is called from create_service, which is wrapped in a transaction.
    """

    new_sms_sender = ServiceSmsSender(sms_sender=sms_sender, service=service, is_default=True)
    db.session.add(new_sms_sender)


@cached(sms_sender_data_cache)
def dao_get_service_sms_sender_by_id(
    service_id: str,
    service_sms_sender_id: str,
) -> ServiceSmsSenderData:
    stmt = select(ServiceSmsSender).where(
        ServiceSmsSender.id == service_sms_sender_id,
        ServiceSmsSender.service_id == service_id,
        ServiceSmsSender.archived.is_(False),
    )
    service_sender = db.session.scalars(stmt).one()

    return ServiceSmsSenderData(
        id=str(service_sender.id),
        service_id=str(service_sender.service_id),
        sms_sender=service_sender.sms_sender,
        is_default=service_sender.is_default,
        inbound_number_id=str(service_sender.inbound_number_id) if service_sender.inbound_number_id else None,
        provider_id=str(service_sender.provider_id) if service_sender.provider_id else None,
        archived=service_sender.archived,
        description=service_sender.description,
        rate_limit=service_sender.rate_limit,
        rate_limit_interval=service_sender.rate_limit_interval,
        sms_sender_specifics=service_sender.sms_sender_specifics,
        created_at=service_sender.created_at.strftime(DATETIME_FORMAT) if service_sender.created_at else None,
        updated_at=service_sender.updated_at.strftime(DATETIME_FORMAT) if service_sender.updated_at else None,
    )


@cached(sms_sender_data_cache)
def dao_get_sms_senders_data_by_service_id(service_id: str) -> list[ServiceSmsSenderData]:
    """Return a cached list of ServiceSmsSenderData objects for a given service_id."""
    stmt = (
        select(ServiceSmsSender)
        .where(ServiceSmsSender.service_id == service_id, ServiceSmsSender.archived.is_(False))
        .order_by(desc(ServiceSmsSender.is_default))
    )
    senders = db.session.scalars(stmt).all()
    return [
        ServiceSmsSenderData(
            id=str(sender.id),
            service_id=str(sender.service_id),
            sms_sender=sender.sms_sender,
            is_default=sender.is_default,
            inbound_number_id=str(sender.inbound_number_id) if sender.inbound_number_id else None,
            provider_id=str(sender.provider_id) if sender.provider_id else None,
            archived=sender.archived,
            description=sender.description,
            rate_limit=sender.rate_limit,
            rate_limit_interval=sender.rate_limit_interval,
            sms_sender_specifics=sender.sms_sender_specifics,
            created_at=sender.created_at.strftime(DATETIME_FORMAT) if sender.created_at else None,
            updated_at=sender.updated_at.strftime(DATETIME_FORMAT) if sender.updated_at else None,
        )
        for sender in senders
    ]


def dao_get_sms_senders_by_service_id(service_id: str) -> list[ServiceSmsSender]:
    """Return a list of ServiceSmsSender ORM objects for a given service_id. Not cached."""
    stmt = (
        select(ServiceSmsSender)
        .where(ServiceSmsSender.service_id == service_id, ServiceSmsSender.archived.is_(False))
        .order_by(desc(ServiceSmsSender.is_default))
    )

    return db.session.scalars(stmt).all()


@cached(sms_sender_data_cache)
def dao_get_service_sms_sender_by_service_id_and_number(
    service_id: str,
    number: str,
) -> Optional[ServiceSmsSenderData]:
    """Return an instance of ServiceSmsSenderData, if available."""
    stmt = select(ServiceSmsSender).where(
        ServiceSmsSender.service_id == service_id,
        ServiceSmsSender.sms_sender == number,
        ServiceSmsSender.archived.is_(False),
    )

    service_sender = db.session.scalars(stmt).first()
    if not service_sender:
        return None
    return ServiceSmsSenderData(
        id=str(service_sender.id),
        service_id=str(service_sender.service_id),
        sms_sender=service_sender.sms_sender,
        is_default=service_sender.is_default,
        inbound_number_id=str(service_sender.inbound_number_id) if service_sender.inbound_number_id else None,
        provider_id=str(service_sender.provider_id) if service_sender.provider_id else None,
        archived=service_sender.archived,
        description=service_sender.description,
        rate_limit=service_sender.rate_limit,
        rate_limit_interval=service_sender.rate_limit_interval,
        sms_sender_specifics=service_sender.sms_sender_specifics,
        created_at=service_sender.created_at.strftime(DATETIME_FORMAT) if service_sender.created_at else None,
        updated_at=service_sender.updated_at.strftime(DATETIME_FORMAT) if service_sender.updated_at else None,
    )


@transactional
def dao_add_sms_sender_for_service(
    service_id,
    sms_sender,
    is_default,
    provider_id,
    description,
    inbound_number_id=None,
    rate_limit=None,
    rate_limit_interval=None,
    sms_sender_specifics={},
) -> ServiceSmsSender:
    default_sms_sender = _get_default_sms_sender_for_service(service_id=service_id)

    if not default_sms_sender and not is_default:
        raise SmsSenderDefaultValidationException('You must have at least one SMS sender as the default.')

    if is_default:
        _set_default_sms_sender_to_not_default(default_sms_sender)

    _validate_rate_limit(None, rate_limit, rate_limit_interval)

    if inbound_number_id is not None:
        inbound_number = _allocate_inbound_number_for_service(service_id, inbound_number_id)

        if inbound_number.number != sms_sender:
            raise SmsSenderInboundNumberIntegrityException(
                f"You cannot create an SMS sender with the number '{sms_sender}' "
                f"and the Inbound Number '{inbound_number.id}' ('{inbound_number.number}')."
            )

    provider_details = _validate_provider(provider_id)

    new_sms_sender = ServiceSmsSender(
        description=description,
        is_default=is_default,
        inbound_number_id=inbound_number_id,
        provider=provider_details,
        provider_id=provider_id,
        rate_limit=rate_limit,
        rate_limit_interval=rate_limit_interval,
        service_id=service_id,
        sms_sender=sms_sender,
        sms_sender_specifics=sms_sender_specifics,
    )

    db.session.add(new_sms_sender)
    return new_sms_sender


def _validate_provider(provider_id: UUID) -> ProviderDetails:
    """Validate the provider_details. This is a helper function when adding or updating an SMS sender.
    It checks the provider exists and raises an Exception if it doesn't.

    Args:
        provider_id (UUID): The ID of the provider to validate.

    Returns:
        ProviderDetails: The provider details.

    Raises:
        SmsSenderProviderValidationException: If the provider doesn't exist.
    """

    provider_details = db.session.get(ProviderDetails, provider_id)

    if provider_details is None:
        raise SmsSenderProviderValidationException(f'No provider details found for id {provider_id}')

    return provider_details


@transactional
def dao_update_service_sms_sender(
    service_id,
    service_sms_sender_id,
    **kwargs,
) -> ServiceSmsSender:
    if 'is_default' in kwargs:
        _handle_default_sms_sender(service_id, service_sms_sender_id, kwargs['is_default'])

    if 'inbound_number_id' in kwargs:
        _allocate_inbound_number_for_service(service_id, kwargs['inbound_number_id'])

    sms_sender_to_update: ServiceSmsSender = db.session.get(ServiceSmsSender, service_sms_sender_id)

    _validate_rate_limit(sms_sender_to_update, kwargs.get('rate_limit'), kwargs.get('rate_limit_interval'))

    if 'sms_sender' in kwargs and sms_sender_to_update.inbound_number_id:
        raise SmsSenderInboundNumberIntegrityException(
            'You cannot update the number for this SMS sender because it has an associated Inbound Number.'
        )

    if 'provider_id' in kwargs:
        _validate_provider(kwargs['provider_id'])

    for key, value in kwargs.items():
        setattr(sms_sender_to_update, key, value)

    db.session.add(sms_sender_to_update)
    return sms_sender_to_update


def _handle_default_sms_sender(service_id: UUID, service_sms_sender_id: UUID, is_default: bool) -> None:
    """Check the default SMS sender.
    This is a helper function when updating an SMS sender. It ensures there is a default SMS sender for the service and
    raises an exception if there won't be a default sender after the update.

    Args:
        service_id (UUID): The ID of the service.
        service_sms_sender_id (UUID): The ID of the SMS sender.
        is_default (bool): Whether the SMS sender should be updated to be the default.

    Raises:
        SmsSenderDefaultValidationException: If there is no default SMS sender for the service.

    """
    default_sms_sender = _get_default_sms_sender_for_service(service_id)

    # ensure there will still be a default sender on the service, else raise an exception
    if service_sms_sender_id == default_sms_sender.id and not is_default:
        raise SmsSenderDefaultValidationException('You must have at least one SMS sender as the default.')

    if is_default:
        _set_default_sms_sender_to_not_default(default_sms_sender)


def _validate_rate_limit(
    sms_sender_to_update: ServiceSmsSender | None,
    rate_limit: int | None,
    rate_limit_interval: int | None,
) -> None:
    """Validate the rate limit and rate limit interval.
    This is a helper function when adding or updating a SMS sender.
    It ensures the rate limit and rate limit interval are valid.

    Args:
        sms_sender_to_update (ServiceSmsSender | None): The SMS sender to update, or None if adding a new SMS sender.
        rate_limit (int | None): The sms sender's rate limit.
        rate_limit_interval (int | None): The sms sender's rate limit interval.

    Raises:
        SmsSenderRateLimitIntegrityException: If the rate limit or rate limit interval is invalid.
    """
    # ensure rate_limit is a positive integer, when included in kwargs
    if rate_limit is not None and rate_limit < 1:
        raise SmsSenderRateLimitIntegrityException('rate_limit cannot be less than 1.')

    # ensure rate_limit_interval is a positive integer, when included in kwargs
    if rate_limit_interval is not None and rate_limit_interval < 1:
        raise SmsSenderRateLimitIntegrityException('rate_limit_interval cannot be less than 1.')

    # only run these checks when updating an existing SMS sender
    if sms_sender_to_update:
        # if rate limit is being updated, ensure rate limit interval is also being updated, or is already valid
        if rate_limit and not rate_limit_interval:
            if not sms_sender_to_update.rate_limit_interval:
                raise SmsSenderRateLimitIntegrityException(
                    'Cannot update sender to have only one of rate limit value and interval.'
                )

        # if rate limit interval is being updated, ensure rate limit is also being updated, or is already valid
        if not rate_limit and rate_limit_interval:
            if not sms_sender_to_update.rate_limit:
                raise SmsSenderRateLimitIntegrityException(
                    'Cannot update sender to have only one of rate limit value and interval.'
                )
    else:
        # when adding a new sender ensure both rate limit and rate limit interval are provided, or neither
        if (rate_limit is None) != (rate_limit_interval is None):
            raise SmsSenderRateLimitIntegrityException('Provide both rate_limit and rate_limit_interval, or neither.')


def _get_default_sms_sender_for_service(service_id) -> Optional[ServiceSmsSender]:
    sms_senders = dao_get_sms_senders_by_service_id(service_id=service_id)
    if sms_senders:
        old_default = [x for x in sms_senders if x.is_default]
        if len(old_default) == 1:
            return old_default[0]
        else:
            raise SmsSenderDefaultValidationException(
                f'There should only be one default sms sender for each service. '
                f'Service {service_id} has {len(old_default)}.'
            )
    return None


def _set_default_sms_sender_to_not_default(existing_default_sms_sender: Optional[ServiceSmsSender]) -> None:
    if existing_default_sms_sender:
        existing_default_sms_sender.is_default = False
        db.session.add(existing_default_sms_sender)


def _allocate_inbound_number_for_service(
    service_id,
    inbound_number_id,
) -> InboundNumber:
    stmt = (
        update(InboundNumber)
        .where(
            InboundNumber.id == inbound_number_id, InboundNumber.active.is_(True), InboundNumber.service_id.is_(None)
        )
        .values(service_id=service_id)
    )

    updated = db.session.execute(stmt)

    if updated.rowcount == 0:
        raise SmsSenderInboundNumberIntegrityException(f'Inbound number: {inbound_number_id} is not available.')

    return db.session.get(InboundNumber, inbound_number_id)


@cached(sms_sender_data_cache)
def dao_get_default_service_sms_sender_by_service_id(service_id: str) -> Optional[ServiceSmsSenderData]:
    """Return the default ServiceSmsSenderData for a given service_id, or None if not found."""
    stmt = select(ServiceSmsSender).where(
        ServiceSmsSender.service_id == service_id,
        ServiceSmsSender.is_default.is_(True),
        ServiceSmsSender.archived.is_(False),
    )
    service_sender = db.session.scalars(stmt).first()
    if not service_sender:
        return None
    return ServiceSmsSenderData(
        id=str(service_sender.id),
        service_id=str(service_sender.service_id),
        sms_sender=service_sender.sms_sender,
        is_default=service_sender.is_default,
        inbound_number_id=str(service_sender.inbound_number_id) if service_sender.inbound_number_id else None,
        provider_id=str(service_sender.provider_id) if service_sender.provider_id else None,
        archived=service_sender.archived,
        description=service_sender.description,
        rate_limit=service_sender.rate_limit,
        rate_limit_interval=service_sender.rate_limit_interval,
        sms_sender_specifics=service_sender.sms_sender_specifics,
        created_at=service_sender.created_at.strftime(DATETIME_FORMAT) if service_sender.created_at else None,
        updated_at=service_sender.updated_at.strftime(DATETIME_FORMAT) if service_sender.updated_at else None,
    )
