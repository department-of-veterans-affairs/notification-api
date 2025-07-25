from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

import datetime
import html
import itertools
import uuid

from app.feature_flags import FeatureFlag, is_feature_enabled
from flask import current_app, url_for

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, and_, select
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.collections import InstrumentedList, attribute_mapped_collection

from notifications_utils.columns import Columns
from notifications_utils.letter_timings import get_letter_timings
from notifications_utils.recipients import (
    InvalidEmailError,
    InvalidPhoneError,
    try_validate_and_format_phone_number,
    validate_email_address,
    ValidatedPhoneNumber,
)
from notifications_utils.template import HTMLEmailTemplate, PlainTextEmailTemplate, SMSMessageTemplate
from notifications_utils.timezones import convert_local_timezone_to_utc, convert_utc_to_local_timezone

from app import encryption
from app.constants import (
    BRANDING_ORG,
    DATETIME_FORMAT,
    DELIVERY_STATUS_CALLBACK_TYPE,
    EMAIL_TYPE,
    EMAIL_AUTH_TYPE,
    FIRETEXT_PROVIDER,
    INVITE_PENDING,
    INVITED_USER_STATUS_TYPES,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    MMG_PROVIDER,
    MOBILE_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_RETURNED_LETTER,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_LETTER_ACCEPTED,
    NOTIFICATION_STATUS_LETTER_RECEIVED,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_TYPE,
    PERMISSION_LIST,
    PINPOINT_PROVIDER,
    SES_PROVIDER,
    SMS_TYPE,
    SNS_PROVIDER,
    TEMPLATE_PROCESS_NORMAL,
    TEMPLATE_TYPES,
    WHITELIST_RECIPIENT_TYPE,
)
from app.db import db
from app.encryption import check_hash, hashpw
from app.history_meta import Versioned
from app.model import User
from app.va.identifier import IdentifierType

# models.py only constants
UNKNOWN_COMPLAINT_TYPE = 'unknown complaint type'
VERIFY_CODE_TYPES = (EMAIL_TYPE, SMS_TYPE)
# models.py only but order dependent
SMS_PROVIDERS = (MMG_PROVIDER, FIRETEXT_PROVIDER, PINPOINT_PROVIDER, SNS_PROVIDER)
EMAIL_PROVIDERS = (SES_PROVIDER,)
PROVIDERS = SMS_PROVIDERS + EMAIL_PROVIDERS

# Model enums
_notification_types = db.Enum(*NOTIFICATION_TYPE, name='notification_type')
_notification_status_types_enum = db.Enum(*NOTIFICATION_STATUS_TYPES, name='notify_status_type')  # Not necessary?
_template_types = db.Enum(*TEMPLATE_TYPES, name='template_type')
_whitelist_recipient_types = db.Enum(*WHITELIST_RECIPIENT_TYPE, name='recipient_type')


def filter_null_value_fields(obj):
    return dict(filter(lambda x: x[1] is not None, obj.items()))


class HistoryModel:
    @classmethod
    def from_original(
        cls,
        original,
    ):
        history = cls()
        history.update_from_original(original)
        return history

    def update_from_original(
        self,
        original,
    ):
        for c in self.__table__.columns:
            # in some cases, columns may have different names to their underlying db column -  so only copy those
            # that we can, and leave it up to subclasses to deal with any oddities/properties etc.
            if hasattr(original, c.name):
                setattr(self, c.name, getattr(original, c.name))
            else:
                current_app.logger.debug('{} has no column {} to copy from'.format(original, c.name))


class ServiceUser(db.Model):
    __tablename__ = 'user_to_service'
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), primary_key=True)

    __table_args__ = (UniqueConstraint('user_id', 'service_id', name='uix_user_to_service'),)


user_to_organisation = db.Table(
    'user_to_organisation',
    db.Model.metadata,
    db.Column('user_id', UUID(as_uuid=True), db.ForeignKey('users.id')),
    db.Column('organisation_id', UUID(as_uuid=True), db.ForeignKey('organisation.id')),
    UniqueConstraint('user_id', 'organisation_id', name='uix_user_to_organisation'),
)

user_folder_permissions = db.Table(
    'user_folder_permissions',
    db.Model.metadata,
    db.Column('user_id', UUID(as_uuid=True), primary_key=True),
    db.Column('template_folder_id', UUID(as_uuid=True), db.ForeignKey('template_folder.id'), primary_key=True),
    db.Column('service_id', UUID(as_uuid=True), primary_key=True),
    db.ForeignKeyConstraint(['user_id', 'service_id'], ['user_to_service.user_id', 'user_to_service.service_id']),
    db.ForeignKeyConstraint(['template_folder_id', 'service_id'], ['template_folder.id', 'template_folder.service_id']),
)


class BrandingTypes(db.Model):
    __tablename__ = 'branding_type'
    name = db.Column(db.String(255), primary_key=True)


class EmailBranding(db.Model):
    __tablename__ = 'email_branding'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    colour = db.Column(db.String(7), nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    text = db.Column(db.String(255), nullable=True)
    brand_type = db.Column(
        db.String(255), db.ForeignKey('branding_type.name'), index=True, nullable=False, default=BRANDING_ORG
    )

    def serialize(self):
        serialized = {
            'id': str(self.id),
            'colour': self.colour,
            'logo': self.logo,
            'name': self.name,
            'text': self.text,
            'brand_type': self.brand_type,
        }

        return serialized


service_email_branding = db.Table(
    'service_email_branding',
    db.Model.metadata,
    # service_id is a primary key as you can only have one email branding per service
    db.Column('service_id', UUID(as_uuid=True), db.ForeignKey('services.id'), primary_key=True, nullable=False),
    db.Column('email_branding_id', UUID(as_uuid=True), db.ForeignKey('email_branding.id'), nullable=False),
)


class ServicePermissionTypes(db.Model):
    __tablename__ = 'service_permission_types'

    name = db.Column(db.String(255), primary_key=True)


class Domain(db.Model):
    __tablename__ = 'domain'
    domain = db.Column(db.String(255), primary_key=True)
    organisation_id = db.Column('organisation_id', UUID(as_uuid=True), db.ForeignKey('organisation.id'), nullable=False)


class OrganisationTypes(db.Model):
    __tablename__ = 'organisation_types'

    name = db.Column(db.String(255), primary_key=True)
    is_crown = db.Column(db.Boolean, nullable=True)
    annual_free_sms_fragment_limit = db.Column(db.BigInteger, nullable=False)


class Organisation(db.Model):
    __tablename__ = 'organisation'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=False)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    agreement_signed = db.Column(db.Boolean, nullable=True)
    agreement_signed_at = db.Column(db.DateTime, nullable=True)
    agreement_signed_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('users.id'),
        nullable=True,
    )
    agreement_signed_by = db.relationship('User')
    agreement_signed_on_behalf_of_name = db.Column(db.String(255), nullable=True)
    agreement_signed_on_behalf_of_email_address = db.Column(db.String(255), nullable=True)
    agreement_signed_version = db.Column(db.Float, nullable=True)
    crown = db.Column(db.Boolean, nullable=True)
    organisation_type = db.Column(
        db.String(255),
        db.ForeignKey('organisation_types.name'),
        unique=False,
        nullable=True,
    )
    request_to_go_live_notes = db.Column(db.Text)

    domains = db.relationship(
        'Domain',
    )

    email_branding = db.relationship('EmailBranding')
    email_branding_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey('email_branding.id'),
        nullable=True,
    )

    @property
    def live_services(self):
        return [service for service in self.services if service.active and not service.restricted]

    @property
    def domain_list(self):
        return [domain.domain for domain in self.domains]

    def serialize(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'active': self.active,
            'crown': self.crown,
            'organisation_type': self.organisation_type,
            'email_branding_id': self.email_branding_id,
            'agreement_signed': self.agreement_signed,
            'agreement_signed_at': self.agreement_signed_at,
            'agreement_signed_by_id': self.agreement_signed_by_id,
            'agreement_signed_on_behalf_of_name': self.agreement_signed_on_behalf_of_name,
            'agreement_signed_on_behalf_of_email_address': self.agreement_signed_on_behalf_of_email_address,
            'agreement_signed_version': self.agreement_signed_version,
            'domains': self.domain_list,
            'request_to_go_live_notes': self.request_to_go_live_notes,
            'count_of_live_services': len(self.live_services),
        }

    def serialize_for_list(self):
        return {
            'name': self.name,
            'id': str(self.id),
            'active': self.active,
            'count_of_live_services': len(self.live_services),
            'domains': self.domain_list,
            'organisation_type': self.organisation_type,
        }


@dataclass
class ProviderDetailsData:
    """
    Used for caching a ProviderDetails instance.
    """

    active: bool
    display_name: str
    identifier: str
    notification_type: str


class ProviderDetails(db.Model):
    __tablename__ = 'provider_details'
    NOTIFICATION_TYPE = [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]
    notification_types = db.Enum(*NOTIFICATION_TYPE, name='notification_type')

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    load_balancing_weight = db.Column(db.Integer, nullable=True)
    notification_type = db.Column(notification_types, nullable=False)
    active = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=True)
    created_by = db.relationship('User')
    supports_international = db.Column(db.Boolean, nullable=False, default=False)


class Service(db.Model, Versioned):
    __tablename__ = 'services'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=True)
    message_limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    research_mode = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=False)
    email_from = db.Column(db.Text, index=False, unique=False, nullable=True)
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    prefix_sms = db.Column(db.Boolean, nullable=False, default=False)
    organisation_type = db.Column(
        db.String(255),
        db.ForeignKey('organisation_types.name'),
        unique=False,
        nullable=True,
    )
    crown = db.Column(db.Boolean, index=False, nullable=True)
    rate_limit = db.Column(db.Integer, index=False, nullable=False, default=3000)
    contact_link = db.Column(db.String(255), nullable=True, unique=False)
    volume_sms = db.Column(db.Integer(), nullable=True, unique=False)
    volume_email = db.Column(db.Integer(), nullable=True, unique=False)
    volume_letter = db.Column(db.Integer(), nullable=True, unique=False)
    consent_to_research = db.Column(db.Boolean, nullable=True)
    count_as_live = db.Column(db.Boolean, nullable=False, default=True)
    go_live_user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    go_live_user = db.relationship('User', foreign_keys=[go_live_user_id])
    go_live_at = db.Column(db.DateTime, nullable=True)
    sending_domain = db.Column(db.String(255), nullable=True, unique=False)
    smtp_user = db.Column(db.String(255), nullable=True, unique=False)

    email_provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), nullable=True)
    sms_provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), nullable=True)

    organisation_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organisation.id'), index=True, nullable=True)
    organisation = db.relationship('Organisation', backref='services')

    p2p_enabled = db.Column(db.Boolean, nullable=True, default=False)

    email_branding = db.relationship(
        'EmailBranding', secondary=service_email_branding, uselist=False, backref=db.backref('services', lazy='dynamic')
    )

    @classmethod
    def from_json(
        cls,
        data,
    ):
        """
        Assumption: data has been validated appropriately.

        Returns a Service object based on the provided data. Deserialises created_by to created_by_id as marshmallow
        would.
        """
        # validate json with marshmallow
        fields = data.copy()

        fields['created_by_id'] = fields.pop('created_by')

        return cls(**fields)

    def get_default_sms_sender(self) -> str | None:
        """
        service_sms_senders is a back reference from the ServiceSmsSender table.
        """
        # there should only be one default sms sender per service
        for sms_sender in self.service_sms_senders:
            if sms_sender.is_default:
                return sms_sender.sms_sender

        return None

    def get_default_sms_sender_id(self):
        """
        service_sms_senders is a back reference from the ServiceSmsSender table.
        """
        # there should only be one default sms sender per service
        for sms_sender in self.service_sms_senders:
            if sms_sender.is_default:
                return sms_sender.id

        return None

    def get_default_letter_contact(self):
        # there should only be one default letter contact per service
        for default_letter_contact in self.letter_contacts:
            if default_letter_contact.is_default:
                return default_letter_contact.contact_block

        return None

    def has_permissions(
        self,
        permissions_to_check_for,
    ):
        if isinstance(permissions_to_check_for, InstrumentedList):
            _permissions_to_check_for = [p.permission for p in permissions_to_check_for]
        elif not isinstance(permissions_to_check_for, list) and not isinstance(permissions_to_check_for, tuple):
            _permissions_to_check_for = (permissions_to_check_for,)
        else:
            _permissions_to_check_for = permissions_to_check_for

        if isinstance(self.permissions, InstrumentedList):
            _permissions = [p.permission for p in self.permissions]
        else:
            _permissions = self.permissions

        return frozenset(_permissions_to_check_for).issubset(frozenset(_permissions))

    def serialize_for_org_dashboard(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'active': self.active,
            'restricted': self.restricted,
            'research_mode': self.research_mode,
        }

    def serialize_for_user(self):
        return {'id': str(self.id), 'name': self.name, 'research_mode': self.research_mode}


# Portal uses this table.  Do not drop it without consulting the front-end team.
class ReplyToInbox(db.Model):
    __tablename__ = 'reply_to_inbox'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inbox = db.Column(db.String, nullable=False)
    service = db.relationship(Service)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), nullable=False, index=True, unique=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)


class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String, nullable=False, index=True)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, index=True, onupdate=datetime.datetime.utcnow)


class TemplateP2PChecklist(db.Model):
    __tablename__ = 'template_p2p_checklist'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), nullable=False, index=True, unique=False)
    checklist = db.Column(JSONB)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)


class AnnualBilling(db.Model):
    __tablename__ = 'annual_billing'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), unique=False, index=True, nullable=False)
    financial_year_start = db.Column(db.Integer, nullable=False, default=True, unique=False)
    free_sms_fragment_limit = db.Column(db.Integer, nullable=False, index=False, unique=False)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    UniqueConstraint('financial_year_start', 'service_id', name='ix_annual_billing_service_id')
    service = db.relationship(Service, backref=db.backref('annual_billing', uselist=True))

    def serialize_free_sms_items(self):
        return {
            'free_sms_fragment_limit': self.free_sms_fragment_limit,
            'financial_year_start': self.financial_year_start,
        }

    def serialize(self):
        def serialize_service():
            return {'id': str(self.service_id), 'name': self.service.name}

        return {
            'id': str(self.id),
            'free_sms_fragment_limit': self.free_sms_fragment_limit,
            'service_id': self.service_id,
            'financial_year_start': self.financial_year_start,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
            'service': serialize_service() if self.service else None,
        }


class InboundNumber(db.Model):
    __tablename__ = 'inbound_numbers'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = db.Column(db.String(12), unique=True, nullable=False)
    provider = db.Column(db.String(), nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=True)
    service = db.relationship(Service, backref=db.backref('inbound_numbers', uselist=True))
    active = db.Column(db.Boolean, index=False, unique=False, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    url_endpoint = db.Column(db.String(), nullable=True)
    self_managed = db.Column(db.Boolean, nullable=False, default=False)
    auth_parameter = db.Column(db.String(), nullable=True)

    def serialize(self):
        return {
            'id': str(self.id),
            'number': self.number,
            'provider': self.provider,
            'service': {
                'id': str(self.service_id),
                'name': self.service.name,
            }
            if self.service
            else None,
            'active': self.active,
            'url_endpoint': self.url_endpoint,
            'self_managed': self.self_managed,
            'auth_parameter': self.auth_parameter,
        }


class ServiceSmsSender(db.Model):
    """Define the service_sms_senders table."""

    __tablename__ = 'service_sms_senders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    description = db.Column(db.String(256))
    inbound_number = db.relationship(InboundNumber, backref=db.backref('inbound_number', uselist=False))
    inbound_number_id = db.Column(UUID(as_uuid=True), db.ForeignKey('inbound_numbers.id'), unique=True, index=True)
    is_default = db.Column(db.Boolean, nullable=False, default=True)
    provider = db.relationship(ProviderDetails, backref=db.backref('provider_details'))
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'))
    rate_limit = db.Column(db.Integer, nullable=True)
    rate_limit_interval = db.Column(db.Integer, nullable=True)
    service = db.relationship(Service, backref=db.backref('service_sms_senders', uselist=True))
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    # sms_sender is intended to be used with boto3's send_text_message method as the OriginationIdentity parameter.
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/pinpoint-sms-voice-v2/client/send_text_message.html
    sms_sender: str = db.Column(
        db.String(256),
        nullable=False,
        doc="This can be the sender's PhoneNumber, PhoneNumberId, PhoneNumberArn, SenderId, SenderIdArn, PoolId, or PoolArn.",
    )
    sms_sender_specifics = db.Column(db.JSON(), doc='A placeholder for any service provider we might want to use.')
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    def serialize(self) -> dict[str, bool | int | str | None]:
        provider = None
        if self.provider_id:
            from app.dao.provider_details_dao import get_provider_details_by_id  # Lazy import to avoid circular import

            provider = get_provider_details_by_id(self.provider_id)
        return {
            'id': str(self.id) if self.id else None,
            'is_default': self.is_default,
            'service_id': str(self.service_id) if self.service_id else None,
            'sms_sender': self.sms_sender,
            'inbound_number_id': str(self.inbound_number_id) if self.inbound_number_id else None,
            'provider_id': str(self.provider_id) if self.provider_id else None,
            'provider_name': getattr(provider, 'display_name', None),
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None,
            'archived': self.archived,
            'description': self.description,
            'rate_limit': self.rate_limit,
            'rate_limit_interval': self.rate_limit_interval,
            'sms_sender_specifics': self.sms_sender_specifics or {},
        }


@dataclass
class ServiceSmsSenderData:
    """
    Used for caching a ServiceSmsSender instance.
    """

    id: str
    service_id: str
    sms_sender: str
    is_default: bool
    inbound_number_id: str | None
    provider_id: str | None
    archived: bool
    description: str | None
    rate_limit: int | None
    rate_limit_interval: int | None
    sms_sender_specifics: dict | None
    created_at: str | None = None
    updated_at: str | None = None

    def serialize(self) -> dict[str, bool | int | str | None]:
        provider = None
        if self.provider_id:
            from app.dao.provider_details_dao import get_provider_details_by_id  # Lazy import to avoid circular import

            provider = get_provider_details_by_id(self.provider_id)
        return {
            'id': self.id,
            'is_default': self.is_default,
            'service_id': self.service_id,
            'sms_sender': self.sms_sender,
            'inbound_number_id': self.inbound_number_id,
            'provider_id': self.provider_id,
            'provider_name': getattr(provider, 'display_name', None),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'archived': self.archived,
            'description': self.description,
            'rate_limit': self.rate_limit,
            'rate_limit_interval': self.rate_limit_interval,
            'sms_sender_specifics': self.sms_sender_specifics or {},
        }


class ServicePermission(db.Model):
    __tablename__ = 'service_permissions'

    service_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey('services.id'), primary_key=True, index=True, nullable=False
    )
    permission = db.Column(
        db.String(255), db.ForeignKey('service_permission_types.name'), index=True, primary_key=True, nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    service_permission_types = db.relationship(Service, backref=db.backref('permissions', cascade='all, delete-orphan'))

    def __repr__(self):
        return '<{} has service permission: {}>'.format(self.service_id, self.permission)


class ServiceWhitelist(db.Model):
    __tablename__ = 'service_whitelist'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='whitelist')
    recipient_type = db.Column(_whitelist_recipient_types, nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @classmethod
    def from_string(
        cls,
        service_id,
        recipient_type,
        recipient,
    ):
        instance = cls(service_id=service_id, recipient_type=recipient_type)

        try:
            if recipient_type == MOBILE_TYPE:
                ValidatedPhoneNumber(recipient)
                instance.recipient = recipient
            elif recipient_type == EMAIL_TYPE:
                validate_email_address(recipient)
                instance.recipient = recipient
            else:
                raise ValueError('Invalid recipient type')
        except InvalidPhoneError:
            raise ValueError('Invalid whitelist: "{}"'.format(recipient))
        except InvalidEmailError:
            raise ValueError('Invalid whitelist: "{}"'.format(recipient))
        else:
            return instance

    def __repr__(self):
        return 'Recipient {} of type: {}'.format(self.recipient, self.recipient_type)


class ServiceCallback(db.Model, Versioned):
    __tablename__ = 'service_callback'

    def __init__(
        self,
        **kwargs,
    ):
        if 'notification_statuses' not in kwargs:
            if kwargs.get('callback_type') == DELIVERY_STATUS_CALLBACK_TYPE:
                self.notification_statuses = NOTIFICATION_STATUS_TYPES_COMPLETED
        super().__init__(**kwargs)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='service_callback')
    url = db.Column(db.String(), nullable=False)
    callback_type = db.Column(db.String(), db.ForeignKey('service_callback_type.name'), nullable=True)
    _bearer_token = db.Column('bearer_token', db.String(), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.relationship('User')
    updated_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    notification_statuses = db.Column('notification_statuses', JSONB, nullable=True)
    callback_channel = db.Column(db.String(), db.ForeignKey('service_callback_channel.channel'), nullable=False)
    include_provider_payload = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint('service_id', 'callback_type', name='uix_service_callback_type'),
        UniqueConstraint('service_id', 'callback_channel', name='uix_service_callback_channel'),
    )

    @property
    def bearer_token(self):
        if self._bearer_token:
            return encryption.decrypt(self._bearer_token)
        return None

    @bearer_token.setter
    def bearer_token(
        self,
        bearer_token,
    ):
        if bearer_token:
            self._bearer_token = encryption.encrypt(str(bearer_token))


@dataclass
class DeliveryStatusCallbackApiData:
    """
    Used for caching a ServiceCallback instance.
    """

    id: str
    service_id: str
    url: str
    # Note that _bearer_token is the encrypted value.
    _bearer_token: str
    include_provider_payload: bool
    callback_channel: str
    callback_type: str | None


class ServiceCallbackType(db.Model):
    __tablename__ = 'service_callback_type'

    name = db.Column(db.String, primary_key=True)


class ServiceCallbackChannel(db.Model):
    __tablename__ = 'service_callback_channel'

    channel = db.Column(db.String, primary_key=True)


class ApiKey(db.Model, Versioned):
    __tablename__ = 'api_keys'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    _secret = db.Column('secret', db.String(255), unique=True, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='api_keys')
    key_type = db.Column(db.String(255), db.ForeignKey('key_types.name'), index=True, nullable=False)
    expiry_date = db.Column(db.DateTime)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)

    @property
    def secret(self):
        if self._secret:
            return encryption.decrypt(self._secret)
        return None

    @secret.setter
    def secret(
        self,
        secret,
    ):
        if secret:
            self._secret = encryption.encrypt(str(secret))


class KeyTypes(db.Model):
    __tablename__ = 'key_types'

    name = db.Column(db.String(255), primary_key=True)


class TemplateProcessTypes(db.Model):
    __tablename__ = 'template_process_type'
    name = db.Column(db.String(255), primary_key=True)


class TemplateFolder(db.Model):
    __tablename__ = 'template_folder'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    parent_id = db.Column(UUID(as_uuid=True), db.ForeignKey('template_folder.id'), nullable=True)

    service = db.relationship('Service', backref='all_template_folders')
    parent = db.relationship('TemplateFolder', remote_side=[id], backref='subfolders')
    users = db.relationship(
        'ServiceUser',
        uselist=True,
        backref=db.backref('folders', foreign_keys='user_folder_permissions.c.template_folder_id'),
        secondary='user_folder_permissions',
        primaryjoin='TemplateFolder.id == user_folder_permissions.c.template_folder_id',
    )

    __table_args__ = (UniqueConstraint('id', 'service_id', name='ix_id_service_id'), {})

    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'service_id': self.service_id,
            'users_with_permission': self.get_users_with_permission(),
        }

    def is_parent_of(
        self,
        other,
    ):
        while other.parent is not None:
            if other.parent == self:
                return True
            other = other.parent
        return False

    def get_users_with_permission(self):
        service_users = self.users
        users_with_permission = [str(service_user.user_id) for service_user in service_users]

        return users_with_permission


template_folder_map = db.Table(
    'template_folder_map',
    db.Model.metadata,
    # template_id is a primary key as a template can only belong in one folder
    db.Column('template_id', UUID(as_uuid=True), db.ForeignKey('templates.id'), primary_key=True, nullable=False),
    db.Column('template_folder_id', UUID(as_uuid=True), db.ForeignKey('template_folder.id'), nullable=False),
)

PRECOMPILED_TEMPLATE_NAME = 'Pre-compiled PDF'


class TemplateBase(db.Model):
    __abstract__ = True

    def __init__(
        self,
        **kwargs,
    ):
        if 'template_type' in kwargs:
            self.template_type = kwargs.pop('template_type')

        super().__init__(**kwargs)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    template_type = db.Column(_template_types, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    content_as_html = db.Column(db.Text, nullable=True)
    content_as_plain_text = db.Column(db.Text, nullable=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    subject = db.Column(db.Text)
    postage = db.Column(db.String, nullable=True)
    reply_to_email = db.Column(db.String(254), nullable=True)

    CheckConstraint(
        """
        CASE WHEN template_type = 'letter' THEN
            postage is not null and postage in ('first', 'second')
        ELSE
            postage is null
        END
    """
    )

    @declared_attr
    def provider_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), nullable=True)

    @declared_attr
    def communication_item_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey('communication_items.id'), nullable=True)

    @declared_attr
    def service_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)

    @declared_attr
    def created_by_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)

    @declared_attr
    def created_by(cls):
        return db.relationship('User')

    @declared_attr
    def process_type(cls):
        return db.Column(
            db.String(255),
            db.ForeignKey('template_process_type.name'),
            index=True,
            nullable=False,
            default=TEMPLATE_PROCESS_NORMAL,
        )

    redact_personalisation = association_proxy('template_redacted', 'redact_personalisation')

    @declared_attr
    def service_letter_contact_id(cls):
        return db.Column(UUID(as_uuid=True), db.ForeignKey('service_letter_contacts.id'), nullable=True)

    @declared_attr
    def service_letter_contact(cls):
        return db.relationship('ServiceLetterContact', viewonly=True)

    @property
    def reply_to(self):
        if self.template_type == LETTER_TYPE:
            return self.service_letter_contact_id
        else:
            return None

    @reply_to.setter
    def reply_to(
        self,
        value,
    ):
        if self.template_type == LETTER_TYPE:
            self.service_letter_contact_id = value
        elif value is None:
            pass
        else:
            raise ValueError('Unable to set sender for {} template'.format(self.template_type))

    def get_reply_to_text(self) -> Optional[str]:
        if self.template_type == SMS_TYPE:
            return try_validate_and_format_phone_number(self.service.get_default_sms_sender())

        return None

    # https://docs.sqlalchemy.org/en/13/orm/extensions/hybrid.html
    # https://stackoverflow.com/questions/55690796/sqlalchemy-typeerror-boolean-value-of-this-clause-is-not-defined/55692795#55692795

    @hybrid_property
    def is_precompiled_letter(self):
        """
        This is for instance level evaluation.
        """

        return self.hidden and self.name == PRECOMPILED_TEMPLATE_NAME and self.template_type == LETTER_TYPE

    @is_precompiled_letter.expression
    def is_precompiled_letter(cls):
        """
        This is for class level evaluation (i.e. for queries).
        """

        return and_(cls.hidden, cls.name == PRECOMPILED_TEMPLATE_NAME, cls.template_type == LETTER_TYPE)

    @is_precompiled_letter.setter
    def is_precompiled_letter(
        self,
        value,
    ):
        pass

    @property
    def html(self) -> str:
        content = None
        if is_feature_enabled(FeatureFlag.STORE_TEMPLATE_CONTENT):
            if self.content_as_html:
                content = self.content_as_html
            else:
                if self.template_type == EMAIL_TYPE:
                    template_object = HTMLEmailTemplate({'content': self.content, 'subject': self.subject})
                    content = str(template_object)

        return content

    def _as_utils_template(self):
        if self.template_type == EMAIL_TYPE:
            return PlainTextEmailTemplate({'content': self.content, 'subject': self.subject})
        if self.template_type == SMS_TYPE:
            return SMSMessageTemplate({'content': self.content})

    def serialize(self):
        serialized = {
            'id': str(self.id),
            'type': self.template_type,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
            'created_by': self.created_by.email_address,
            'version': self.version,
            'body': self.content,
            'html': self.html,
            'plain_text': self.content_as_plain_text,
            'subject': self.subject if self.template_type != SMS_TYPE else None,
            'name': self.name,
            'personalisation': {
                key: {
                    'required': True,
                }
                for key in self._as_utils_template().placeholder_names
            },
            'postage': self.postage,
        }

        return serialized


class Template(TemplateBase):
    __tablename__ = 'templates'

    service = db.relationship('Service', backref='templates')
    version = db.Column(db.Integer, default=0, nullable=False)

    folder = db.relationship(
        'TemplateFolder',
        secondary=template_folder_map,
        uselist=False,
        # eagerly load the folder whenever the template object is fetched
        lazy='joined',
        backref=db.backref('templates'),
    )

    def get_link(self):
        # TODO: use "/v2/" route once available
        return url_for(
            'template.get_template_by_id_and_service_id',
            service_id=self.service_id,
            template_id=self.id,
            _external=True,
        )

    @classmethod
    def from_json(
        cls,
        data,
        folder,
    ):
        """
        Assumption: data has been validated appropriately.
        Returns a Template object based on the provided data.
        """
        fields = data.copy()

        fields['created_by_id'] = fields.pop('created_by')
        fields['service_id'] = fields.pop('service')
        fields['folder'] = folder
        return cls(**fields)


class TemplateRedacted(db.Model):
    __tablename__ = 'template_redacted'

    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), primary_key=True, nullable=False)
    redact_personalisation = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, index=True)
    updated_by = db.relationship('User')

    # uselist=False as this is a one-to-one relationship
    template = db.relationship('Template', uselist=False, backref=db.backref('template_redacted', uselist=False))


class TemplateHistory(TemplateBase):
    __tablename__ = 'templates_history'

    service = db.relationship('Service')
    version = db.Column(db.Integer, primary_key=True, nullable=False)

    @declared_attr
    def template_redacted(cls):
        return db.relationship(
            'TemplateRedacted', foreign_keys=[cls.id], primaryjoin='TemplateRedacted.template_id == TemplateHistory.id'
        )

    def get_link(self):
        return url_for('v2_template.get_template_by_id', template_id=self.id, version=self.version, _external=True)


class PromotedTemplate(db.Model):
    __tablename__ = 'promoted_templates'

    service = db.relationship('Service')
    template = db.relationship('Template')

    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), nullable=False, index=True, unique=False)
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), nullable=False, index=True, unique=False)
    promoted_service_id = db.Column(UUID(as_uuid=True), nullable=True)
    promoted_template_id = db.Column(UUID(as_uuid=True), nullable=True)
    promoted_template_content_digest = db.Column(db.Text(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)
    expected_cadence = db.Column(db.Text(), nullable=True)


class ProviderRates(db.Model):
    __tablename__ = 'provider_rates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valid_from = db.Column(db.DateTime, nullable=False)
    rate = db.Column(db.Numeric(), nullable=False)
    provider_id = db.Column(UUID(as_uuid=True), db.ForeignKey('provider_details.id'), index=True, nullable=False)
    provider = db.relationship('ProviderDetails', backref=db.backref('provider_rates', lazy='dynamic'))


class ProviderDetailsHistory(db.Model, HistoryModel):
    __tablename__ = 'provider_details_history'
    notification_types = db.Enum(*NOTIFICATION_TYPE, name='notification_type')

    id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    load_balancing_weight = db.Column(db.Integer, nullable=True)
    notification_type = db.Column(notification_types, nullable=False)
    active = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.Integer, primary_key=True, nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=True)
    created_by = db.relationship('User')
    supports_international = db.Column(db.Boolean, nullable=False, default=False)


class JobStatus(db.Model):
    __tablename__ = 'job_status'

    name = db.Column(db.String(255), primary_key=True)


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_file_name = db.Column(db.String, nullable=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=False)
    service = db.relationship('Service', backref=db.backref('jobs', lazy='dynamic'))
    template_id = db.Column(UUID(as_uuid=True), db.ForeignKey('templates.id'), index=True, unique=False)
    template = db.relationship('Template', backref=db.backref('jobs', lazy='dynamic'))
    template_version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    notification_count = db.Column(db.Integer, nullable=False)
    notifications_sent = db.Column(db.Integer, nullable=False, default=0)
    notifications_delivered = db.Column(db.Integer, nullable=False, default=0)
    notifications_failed = db.Column(db.Integer, nullable=False, default=0)

    processing_started = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    processing_finished = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=True)
    scheduled_for = db.Column(db.DateTime, index=True, unique=False, nullable=True)
    job_status = db.Column(
        db.String(255), db.ForeignKey('job_status.name'), index=True, nullable=False, default='pending'
    )
    archived = db.Column(db.Boolean, nullable=False, default=False)


class VerifyCode(db.Model):
    __tablename__ = 'verify_codes'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    user = db.relationship('User', backref=db.backref('verify_codes', lazy='dynamic'))
    _code = db.Column(db.String, nullable=False)
    code_type = db.Column(
        db.Enum(*VERIFY_CODE_TYPES, name='verify_code_types'), index=False, unique=False, nullable=False
    )
    expiry_datetime = db.Column(db.DateTime, nullable=False)
    code_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)

    @property
    def code(self):
        raise AttributeError('Code not readable')

    @code.setter
    def code(
        self,
        cde,
    ):
        self._code = hashpw(cde)

    def check_code(
        self,
        cde,
    ):
        return check_hash(cde, self._code)


class NotificationStatusTypes(db.Model):
    __tablename__ = 'notification_status_types'

    name = db.Column(db.String(), primary_key=True)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    to = db.Column(db.String, nullable=True)
    normalised_to = db.Column(db.String, nullable=True)
    job_id = db.Column(UUID(as_uuid=True), db.ForeignKey('jobs.id'), index=True, unique=False)
    job = db.relationship('Job', backref=db.backref('notifications', lazy='dynamic'))
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    template_id = db.Column(UUID(as_uuid=True), index=True, unique=False)
    template_version = db.Column(db.Integer, nullable=False)
    template = db.relationship('TemplateHistory')
    api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey('api_keys.id'), index=True, unique=False)
    api_key = db.relationship('ApiKey')
    key_type = db.Column(db.String, db.ForeignKey('key_types.name'), index=True, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = db.Column(_notification_types, index=True, nullable=False)
    created_at = db.Column(db.DateTime, index=True, unique=False, nullable=False)
    sent_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    status = db.Column(
        'notification_status',
        db.String,
        db.ForeignKey('notification_status_types.name'),
        index=True,
        nullable=True,
        default='created',
        key='status',  # http://docs.sqlalchemy.org/en/latest/core/metadata.html#sqlalchemy.schema.Column
    )

    # This is an ID from a provider, such as SES (e-mail) or Pinpoint (SMS).
    reference = db.Column(db.String, nullable=True, index=True)

    # This is an ID optionally provided in POST data by a VA service (a.k.a. the client).
    client_reference = db.Column(db.String, index=True, nullable=True)

    _personalisation = db.Column(db.String, nullable=True)
    scheduled_notification = db.relationship('ScheduledNotification', uselist=False)

    international = db.Column(db.Boolean, nullable=False, default=False)
    phone_prefix = db.Column(db.String, nullable=True)
    rate_multiplier = db.Column(db.Float(asdecimal=False), nullable=True)

    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)

    sms_sender = db.relationship(ServiceSmsSender)
    sms_sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey('service_sms_senders.id'), nullable=True)

    reply_to_text: str | None = db.Column(db.String, nullable=True)
    status_reason = db.Column(db.String, nullable=True)

    # These attributes are for SMS billing stats.  AWS Pinpoint relays price in millicents.
    #   ex. 645.0 millicents -> 0.654 cents -> $0.00645
    # A message that exceeds the SMS length limit is broken into "segments."
    segments_count = db.Column(db.Integer, nullable=False, default=0)
    cost_in_millicents = db.Column(db.Float, nullable=False, default=0)

    postage = db.Column(db.String, nullable=True)
    billing_code = db.Column(db.String(256), nullable=True)
    callback_url = db.Column(db.String(255), nullable=True)

    CheckConstraint(
        """
        CASE WHEN notification_type = 'letter' THEN
            postage is not null and postage in ('first', 'second')
        ELSE
            postage is null
        END
    """
    )

    recipient_identifiers = db.relationship(
        'RecipientIdentifier', collection_class=attribute_mapped_collection('id_type'), cascade='all, delete-orphan'
    )

    __table_args__ = (
        db.ForeignKeyConstraint(
            ['template_id', 'template_version'],
            ['templates_history.id', 'templates_history.version'],
        ),
        {},
    )

    @property
    def communication_item(self) -> Optional['CommunicationItem']:
        if self.template and self.template.communication_item_id:
            communication_item = db.session.scalar(
                select(CommunicationItem).where(CommunicationItem.id == self.template.communication_item_id)
            )
            return communication_item

    @property
    def va_profile_item_id(self):
        if self.communication_item:
            return self.communication_item.va_profile_item_id

    @property
    def default_send(self):
        if self.communication_item:
            return self.communication_item.default_send_indicator
        return True

    @property
    def personalisation(self):
        if self._personalisation:
            return encryption.decrypt(self._personalisation)
        return {}

    @personalisation.setter
    def personalisation(
        self,
        personalisation,
    ):
        self._personalisation = encryption.encrypt(personalisation or {})

    def completed_at(self):
        if self.status in NOTIFICATION_STATUS_TYPES_COMPLETED:
            return self.updated_at.strftime(DATETIME_FORMAT)

        return None

    @staticmethod
    def substitute_status(status_or_statuses):
        """
        static function that takes a status or list of statuses and substitutes our new failure types if it finds
        the deprecated one

        > IN
        'failed'

        < OUT
        ['temporary-failure', 'permanent-failure']

        -

        > IN
        ['failed', 'created', 'accepted']

        < OUT
        ['temporary-failure', 'permanent-failure', 'created', 'sending']


        -

        > IN
        'delivered'

        < OUT
        ['received']

        :param status_or_statuses: a single status or list of statuses
        :return: a single status or list with the current failure statuses substituted for 'failure'
        """

        def _substitute_status_str(_status):
            return (
                NOTIFICATION_STATUS_TYPES_FAILED
                if _status == NOTIFICATION_FAILED
                else [NOTIFICATION_CREATED, NOTIFICATION_SENDING]
                if _status == NOTIFICATION_STATUS_LETTER_ACCEPTED
                else NOTIFICATION_DELIVERED
                if _status == NOTIFICATION_STATUS_LETTER_RECEIVED
                else [_status]
            )

        def _substitute_status_seq(_statuses):
            return list(set(itertools.chain.from_iterable(_substitute_status_str(status) for status in _statuses)))

        if isinstance(status_or_statuses, str):
            return _substitute_status_str(status_or_statuses)
        return _substitute_status_seq(status_or_statuses)

    @property
    def content(self):
        from app.utils import get_template_instance

        template_object = get_template_instance(self.template.__dict__, {k: '<redacted>' for k in self.personalisation})
        return str(template_object)

    @property
    def subject(self):
        from app.utils import get_template_instance

        if self.notification_type != SMS_TYPE:
            template_object = get_template_instance(
                self.template.__dict__, {k: '<redacted>' for k in self.personalisation}
            )
            return html.unescape(str(template_object.subject))

    @property
    def formatted_status(self):
        return {
            'email': {
                'failed': 'Failed',
                'temporary-failure': 'Inbox not accepting messages right now',
                'permanent-failure': "Email address doesn't exist",
                'delivered': 'Delivered',
                'sending': 'Sending',
                'created': 'Sending',
                'sent': 'Delivered',
            },
            'sms': {
                'failed': 'Failed',
                'temporary-failure': 'Phone not accepting messages right now',
                'permanent-failure': "Phone number doesn't exist",
                'delivered': 'Delivered',
                'sending': 'Sending',
                'created': 'Sending',
                'sent': 'Sent internationally',
            },
            'letter': {
                'sending': 'Accepted',
                'created': 'Accepted',
                'delivered': 'Received',
                'returned-letter': 'Returned',
            },
        }[self.template.template_type].get(self.status, self.status)

    def get_letter_status(self):
        """
        Return the notification_status, as we should present for letters. The distinction between created and sending is
        a bit more confusing for letters, not to mention that there's no concept of temporary or permanent failure yet.


        """
        # this should only ever be called for letter notifications - it makes no sense otherwise and I'd rather not
        # get the two code flows mixed up at all
        assert self.notification_type == LETTER_TYPE

        if self.status in [NOTIFICATION_CREATED, NOTIFICATION_SENDING]:
            return NOTIFICATION_STATUS_LETTER_ACCEPTED
        elif self.status in [NOTIFICATION_DELIVERED, NOTIFICATION_RETURNED_LETTER]:
            return NOTIFICATION_STATUS_LETTER_RECEIVED
        else:
            # Currently can only be pending-virus-check OR validation-failed
            return self.status

    def get_created_by_name(self):
        if self.created_by:
            return self.created_by.name
        else:
            return None

    def get_created_by_email_address(self):
        if self.created_by:
            return self.created_by.email_address
        else:
            return None

    def serialize_for_csv(self):
        created_at_in_bst = convert_utc_to_local_timezone(self.created_at)
        serialized = {
            'row_number': '' if self.job_row_number is None else self.job_row_number + 1,
            'recipient': self.to,
            'template_name': self.template.name,
            'template_type': self.template.template_type,
            'job_name': self.job.original_file_name if self.job else '',
            'status': self.formatted_status,
            'created_at': created_at_in_bst.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by_name': self.get_created_by_name(),
            'created_by_email_address': self.get_created_by_email_address(),
        }

        return serialized

    def serialize_permanent_failure(self):
        return {
            'billing_code': self.billing_code,
            'completed_at': self.completed_at(),
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'id': str(self.id),
            'notification_type': self.notification_type,
            'personalisation': self.personalisation,
            'email_address': self.to if self.notification_type == EMAIL_TYPE else None,
            'phone_number': self.to if self.notification_type == SMS_TYPE else None,
            'reference': self.reference,
            'sms_sender_id': str(self.sms_sender_id),
            'status': self.status,
            'status_reason': self.status_reason,
            'template': {'id': str(self.template_id), 'version': self.template_version},
            'type': self.notification_type,
        }

    def serialize(self):
        template_dict = {'version': self.template.version, 'id': self.template.id, 'uri': self.template.get_link()}

        serialized = {
            'id': self.id,
            'reference': self.client_reference,
            'provider_reference': self.reference,
            'email_address': self.to if self.notification_type == EMAIL_TYPE else None,
            'phone_number': self.to if self.notification_type == SMS_TYPE else None,
            'line_1': None,
            'line_2': None,
            'line_3': None,
            'line_4': None,
            'line_5': None,
            'line_6': None,
            'postcode': None,
            'type': self.notification_type,
            'status': self.get_letter_status() if self.notification_type == LETTER_TYPE else self.status,
            'status_reason': self.status_reason,
            'template': template_dict,
            'body': self.content,
            'subject': self.subject,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'created_by_name': self.get_created_by_name(),
            'sent_at': self.sent_at.strftime(DATETIME_FORMAT) if self.sent_at else None,
            'sent_by': self.sent_by if self.sent_by else None,
            'completed_at': self.completed_at(),
            'scheduled_for': (
                convert_local_timezone_to_utc(self.scheduled_notification.scheduled_for).strftime(DATETIME_FORMAT)
                if self.scheduled_notification
                else None
            ),
            'postage': self.postage,
            'recipient_identifiers': [
                {
                    'id_type': recipient_identifier.id_type,
                    'id_value': (
                        '<redacted>'
                        if (recipient_identifier.id_type == IdentifierType.ICN.value)
                        else recipient_identifier.id_value
                    ),
                }
                for recipient_identifier in self.recipient_identifiers.values()
            ],
            'billing_code': self.billing_code,
            'sms_sender_id': self.sms_sender_id,
            'segments_count': self.segments_count,
            'cost_in_millicents': self.cost_in_millicents,
            'callback_url': self.callback_url,
        }

        if self.notification_type == LETTER_TYPE:
            col = Columns(self.personalisation)
            serialized['line_1'] = col.get('address_line_1')
            serialized['line_2'] = col.get('address_line_2')
            serialized['line_3'] = col.get('address_line_3')
            serialized['line_4'] = col.get('address_line_4')
            serialized['line_5'] = col.get('address_line_5')
            serialized['line_6'] = col.get('address_line_6')
            serialized['postcode'] = col.get('postcode')
            serialized['estimated_delivery'] = get_letter_timings(
                serialized['created_at'], postage=self.postage
            ).earliest_delivery.strftime(DATETIME_FORMAT)

        return serialized


class NotificationHistory(db.Model, HistoryModel):
    __tablename__ = 'notification_history'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    job_id = db.Column(UUID(as_uuid=True), db.ForeignKey('jobs.id'), index=True, unique=False)
    job = db.relationship('Job')
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    template_id = db.Column(UUID(as_uuid=True), index=True, unique=False)
    template_version = db.Column(db.Integer, nullable=False)
    api_key_id = db.Column(UUID(as_uuid=True), db.ForeignKey('api_keys.id'), index=True, unique=False)
    api_key = db.relationship('ApiKey')
    key_type = db.Column(db.String, db.ForeignKey('key_types.name'), index=True, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = db.Column(_notification_types, index=True, nullable=False)
    created_at = db.Column(db.DateTime, index=True, unique=False, nullable=False)
    sent_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    updated_at = db.Column(db.DateTime, index=False, unique=False, nullable=True, onupdate=datetime.datetime.utcnow)
    status = db.Column(
        'notification_status',
        db.String,
        db.ForeignKey('notification_status_types.name'),
        index=True,
        nullable=True,
        default='created',
        key='status',  # http://docs.sqlalchemy.org/en/latest/core/metadata.html#sqlalchemy.schema.Column
    )
    reference = db.Column(db.String, nullable=True, index=True)
    client_reference = db.Column(db.String, nullable=True)

    international = db.Column(db.Boolean, nullable=False, default=False)
    phone_prefix = db.Column(db.String, nullable=True)
    rate_multiplier = db.Column(db.Float(asdecimal=False), nullable=True)

    created_by = db.relationship('User')
    created_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)

    sms_sender = db.relationship(ServiceSmsSender)
    sms_sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey('service_sms_senders.id'), nullable=True)

    segments_count = db.Column(db.Integer, nullable=False, default=0)
    cost_in_millicents = db.Column(db.Float, nullable=False, default=0)

    postage = db.Column(db.String, nullable=True)
    status_reason = db.Column(db.String, nullable=True)
    billing_code = db.Column(db.String(256), nullable=True)
    CheckConstraint(
        """
        CASE WHEN notification_type = 'letter' THEN
            postage is not null and postage in ('first', 'second')
        ELSE
            postage is null
        END
    """
    )

    __table_args__ = (
        db.ForeignKeyConstraint(
            ['template_id', 'template_version'],
            ['templates_history.id', 'templates_history.version'],
        ),
        {},
    )

    @classmethod
    def from_original(
        cls,
        notification,
    ):
        history = super().from_original(notification)
        history.status = notification.status
        return history

    def update_from_original(
        self,
        original,
    ):
        super().update_from_original(original)
        self.status = original.status


class ScheduledNotification(db.Model):
    __tablename__ = 'scheduled_notifications'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = db.Column(UUID(as_uuid=True), db.ForeignKey('notifications.id'), index=True, nullable=False)
    scheduled_for = db.Column(db.DateTime, index=False, nullable=False)
    pending = db.Column(db.Boolean, nullable=False, default=True)


class RecipientIdentifier(db.Model):
    __tablename__ = 'recipient_identifiers'
    notification_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey('notifications.id', ondelete='cascade'), primary_key=True, nullable=False
    )
    id_type = db.Column(
        db.Enum(*IdentifierType.values(), name='id_types'),
        primary_key=True,
        nullable=False,
        default=IdentifierType.VA_PROFILE_ID.value,
    )
    id_value = db.Column(db.String, primary_key=True, nullable=False)


class InviteStatusType(db.Model):
    __tablename__ = 'invite_status_type'

    name = db.Column(db.String, primary_key=True)


class InvitedUser(db.Model):
    __tablename__ = 'invited_users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    from_user = db.relationship('User')
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False)
    service = db.relationship('Service')
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    status = db.Column(
        db.Enum(*INVITED_USER_STATUS_TYPES, name='invited_users_status_types'), nullable=False, default=INVITE_PENDING
    )
    permissions = db.Column(db.String, nullable=False)
    auth_type = db.Column(
        db.String, db.ForeignKey('auth_type.name'), index=True, nullable=False, default=EMAIL_AUTH_TYPE
    )
    folder_permissions = db.Column(JSONB(none_as_null=True), nullable=False, default=[])

    # would like to have used properties for this but haven't found a way to make them
    # play nice with marshmallow yet
    def get_permissions(self):
        return self.permissions.split(',')


class InvitedOrganisationUser(db.Model):
    __tablename__ = 'invited_organisation_users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    invited_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    invited_by = db.relationship('User')
    organisation_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organisation.id'), nullable=False)
    organisation = db.relationship('Organisation')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

    status = db.Column(db.String, db.ForeignKey('invite_status_type.name'), nullable=False, default=INVITE_PENDING)

    def serialize(self):
        return {
            'id': str(self.id),
            'email_address': self.email_address,
            'invited_by': str(self.invited_by_id),
            'organisation': str(self.organisation_id),
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'status': self.status,
        }


class Permission(db.Model):
    __tablename__ = 'permissions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Service id is optional, if the service is omitted we will assume the permission is not service specific.
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, unique=False, nullable=True)
    service = db.relationship('Service')
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), index=True, nullable=False)
    user = db.relationship('User')
    permission = db.Column(
        db.Enum(*PERMISSION_LIST, name='permission_types'), index=False, unique=False, nullable=False
    )
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint('service_id', 'user_id', 'permission', name='uix_service_user_permission'),)


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, index=False, unique=False, nullable=False, default=datetime.datetime.utcnow)
    data = db.Column(JSON, nullable=False)


class Rate(db.Model):
    __tablename__ = 'rates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valid_from = db.Column(db.DateTime, nullable=False)
    rate = db.Column(db.Float(asdecimal=False), nullable=False)
    notification_type = db.Column(_notification_types, index=True, nullable=False)

    def __str__(self):
        the_string = '{}'.format(self.rate)
        the_string += ' {}'.format(self.notification_type)
        the_string += ' {}'.format(self.valid_from)
        return the_string


class InboundSms(db.Model):
    __tablename__ = 'inbound_sms'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), index=True, nullable=False)
    service = db.relationship('Service', backref='inbound_sms')

    notify_number = db.Column(db.String, nullable=False)  # the service's number, that the msg was sent to
    user_number = db.Column(db.String, nullable=False, index=True)  # the end user's number, that the msg was sent from
    provider_date = db.Column(db.DateTime)
    provider_reference = db.Column(db.String)
    provider = db.Column(db.String, nullable=False)
    _content = db.Column('content', db.String, nullable=False)

    @property
    def content(self):
        return encryption.decrypt(self._content)

    @content.setter
    def content(
        self,
        content,
    ):
        self._content = encryption.encrypt(content)

    def serialize(self):
        return {
            'id': str(self.id),
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'service_id': str(self.service_id),
            'notify_number': self.notify_number,
            'user_number': self.user_number,
            'content': self.content,
        }


class LetterRate(db.Model):
    __tablename__ = 'letter_rates'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    sheet_count = db.Column(db.Integer, nullable=False)  # double sided sheet
    rate = db.Column(db.Numeric(), nullable=False)
    crown = db.Column(db.Boolean, nullable=False)
    post_class = db.Column(db.String, nullable=False)


class ServiceLetterContact(db.Model):
    __tablename__ = 'service_letter_contacts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), unique=False, index=True, nullable=False)
    service = db.relationship(Service, backref=db.backref('letter_contacts'))

    contact_block = db.Column(db.Text, nullable=False, index=False, unique=False)
    is_default = db.Column(db.Boolean, nullable=False, default=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    def serialize(self):
        return {
            'id': str(self.id),
            'service_id': str(self.service_id),
            'contact_block': self.contact_block,
            'is_default': self.is_default,
            'archived': self.archived,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
        }


class AuthType(db.Model):
    __tablename__ = 'auth_type'

    name = db.Column(db.String, primary_key=True)


class DailySortedLetter(db.Model):
    __tablename__ = 'daily_sorted_letter'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    billing_day = db.Column(db.Date, nullable=False, index=True)
    file_name = db.Column(db.String, nullable=True, index=True)
    unsorted_count = db.Column(db.Integer, nullable=False, default=0)
    sorted_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint('file_name', 'billing_day', name='uix_file_name_billing_day'),)


class FactBilling(db.Model):
    __tablename__ = 'ft_billing'

    bst_date = db.Column(db.Date, nullable=False, primary_key=True, index=True)
    template_id = db.Column(UUID(as_uuid=True), nullable=False, primary_key=True, index=True)
    service_id = db.Column(UUID(as_uuid=True), nullable=False, primary_key=True, index=True)
    notification_type = db.Column(db.Text, nullable=False, primary_key=True)
    provider = db.Column(db.Text, nullable=False, primary_key=True)
    rate_multiplier = db.Column(db.Integer(), nullable=False, primary_key=True)
    international = db.Column(db.Boolean, nullable=False, primary_key=True)
    rate = db.Column(db.Numeric(), nullable=False, primary_key=True)
    postage = db.Column(db.String, nullable=False, primary_key=True)
    billable_units = db.Column(db.Integer(), nullable=True)
    notifications_sent = db.Column(db.Integer(), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)


class DateTimeDimension(db.Model):
    __tablename__ = 'dm_datetime'
    bst_date = db.Column(db.Date, nullable=False, primary_key=True, index=True)
    year = db.Column(db.Integer(), nullable=False)
    month = db.Column(db.Integer(), nullable=False)
    month_name = db.Column(db.Text(), nullable=False)
    day = db.Column(db.Integer(), nullable=False)
    bst_day = db.Column(db.Integer(), nullable=False)
    day_of_year = db.Column(db.Integer(), nullable=False)
    week_day_name = db.Column(db.Text(), nullable=False)
    calendar_week = db.Column(db.Integer(), nullable=False)
    quartal = db.Column(db.Text(), nullable=False)
    year_quartal = db.Column(db.Text(), nullable=False)
    year_month = db.Column(db.Text(), nullable=False)
    year_calendar_week = db.Column(db.Text(), nullable=False)
    financial_year = db.Column(db.Integer(), nullable=False)
    utc_daytime_start = db.Column(db.DateTime, nullable=False)
    utc_daytime_end = db.Column(db.DateTime, nullable=False)


Index('ix_dm_datetime_yearmonth', DateTimeDimension.year, DateTimeDimension.month)


class FactNotificationStatus(db.Model):
    __tablename__ = 'ft_notification_status'

    bst_date = db.Column(db.Date, index=True, primary_key=True, nullable=False, default=datetime.date.today)
    template_id = db.Column(UUID(as_uuid=True), primary_key=True, index=True, nullable=False, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
        nullable=False,
        default=uuid.uuid4,
    )
    job_id = db.Column(UUID(as_uuid=True), primary_key=True, index=True, nullable=False, default=uuid.uuid4)
    notification_type = db.Column(db.Text, primary_key=True, nullable=False, default=SMS_TYPE)
    key_type = db.Column(db.Text, primary_key=True, nullable=False, default=KEY_TYPE_NORMAL)
    notification_status = db.Column(db.Text, primary_key=True, nullable=False, default=NOTIFICATION_CREATED)
    status_reason = db.Column(db.Text, nullable=False, default='')
    notification_count = db.Column(db.Integer(), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)


class Complaint(db.Model):
    __tablename__ = 'complaints'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey('notification_history.id'), index=True, nullable=False
    )
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), unique=False, index=True, nullable=False)
    service = db.relationship(Service, backref=db.backref('complaints'))
    feedback_id = db.Column(db.Text, nullable=True)
    complaint_type = db.Column(db.Text, nullable=True, default=UNKNOWN_COMPLAINT_TYPE)
    complaint_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

    def serialize(self):
        return {
            'id': str(self.id),
            'notification_id': str(self.notification_id),
            'service_id': str(self.service_id),
            'service_name': self.service.name,
            'feedback_id': str(self.feedback_id),
            'complaint_type': self.complaint_type,
            'complaint_date': self.complaint_date.strftime(DATETIME_FORMAT) if self.complaint_date else None,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
        }


class ServiceDataRetention(db.Model):
    """
    For a unique combination of a service and a notification type, record the number of days to retain
    a notification.
    """

    __tablename__ = 'service_data_retention'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), unique=False, index=True, nullable=False)
    service = db.relationship(Service, backref=db.backref('service_data_retention'))
    notification_type = db.Column(_notification_types, nullable=False)
    days_of_retention = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint('service_id', 'notification_type', name='uix_service_data_retention'),)

    def serialize(self):
        return {
            'id': str(self.id),
            'service_id': str(self.service_id),
            'service_name': self.service.name,
            'notification_type': self.notification_type,
            'days_of_retention': self.days_of_retention,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
        }


class Fido2Key(db.Model):
    __tablename__ = 'fido2_keys'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), unique=False, index=True, nullable=False)
    user = db.relationship(User, backref=db.backref('fido2_keys'))
    name = db.Column(db.String, nullable=False, index=False, unique=False)
    key = db.Column(db.Text, nullable=False, index=False, unique=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    def serialize(self):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'name': self.name,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
        }


class Fido2Session(db.Model):
    __tablename__ = 'fido2_sessions'
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True, unique=True, index=True, nullable=False
    )
    user = db.relationship(User, backref=db.backref('fido2_sessions'))
    session = db.Column(db.Text, nullable=False, index=False, unique=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)


class LoginEvent(db.Model):
    __tablename__ = 'login_events'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), unique=False, index=True, nullable=False)
    user = db.relationship(User, backref=db.backref('login_events'))
    data = db.Column(JSONB(none_as_null=True), nullable=False, default={})
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    def serialize(self):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'data': self.data,
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
        }


class CommunicationItem(db.Model):
    __tablename__ = 'communication_items'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    default_send_indicator = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    va_profile_item_id = db.Column(db.Integer, nullable=False, unique=True)


class VAProfileLocalCache(db.Model):
    """
    VA Notify caches person IDs to lighten the load on the MPI databse.
    """

    id = db.Column(db.Integer, primary_key=True)
    allowed = db.Column(db.Boolean, nullable=False)
    va_profile_id = db.Column(db.BigInteger, nullable=False)
    communication_item_id = db.Column(db.Integer, nullable=False)
    communication_channel_id = db.Column(db.Integer, nullable=False)
    source_datetime = db.Column(db.DateTime, nullable=False)

    participant_id = db.Column(db.BigInteger, nullable=True)
    has_duplicate_mappings = db.Column(db.Boolean, nullable=False, default=False)
    notification_id = db.Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint('va_profile_id', 'communication_item_id', 'communication_channel_id', name='uix_veteran_id'),
    )


class UserServiceRoles(db.Model):
    __tablename__ = 'user_service_roles'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), unique=False, index=True, nullable=False)
    role = db.Column(db.String(255), nullable=False, index=False, unique=False)
    service_id = db.Column(UUID(as_uuid=True), db.ForeignKey('services.id'), unique=False, index=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.datetime.utcnow)

    def serialize(self):
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'role': self.role,
            'service_id': str(self.service_id),
            'created_at': self.created_at.strftime(DATETIME_FORMAT),
            'updated_at': self.updated_at.strftime(DATETIME_FORMAT) if self.updated_at else None,
        }


class NotificationFailures(db.Model):
    """
    A SQLAlchemy model representing the 'notification_failures' table. This table captures infrequent,
    invalid v3 requests that passed schema checks but failed during processing and could not be added
    to the notifications table.

    Attributes:
        notification_id (int): The primary key of the table.
        created_at (DateTime): Record date and time of creation. This field will be used for pg_cron
        job delete records older then 30 days
        body (JSONB): Column used to store the details of the notification failure in a JSON object.

    Methods:
        serialize: Converts the 'body' attribute to a dictionary for easier consumption.
    """

    __tablename__ = 'notification_failures'

    notification_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    body = db.Column(JSONB, nullable=False)

    def serialize(self) -> Dict[str, Any]:
        return self.body
