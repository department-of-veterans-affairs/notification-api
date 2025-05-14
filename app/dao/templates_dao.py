import uuid
from dataclasses import dataclass
from datetime import datetime

from cachetools import cached, TTLCache
from sqlalchemy import asc, desc, func, select, update

from app import db
from app.constants import EMAIL_TYPE
from app.dao.dao_utils import (
    transactional,
    version_class,
    VersionOptions,
)
from app.feature_flags import FeatureFlag, is_feature_enabled
from app.models import (
    Template,
    TemplateHistory,
    TemplateRedacted,
)
from app.utils import generate_html_email_content

from typing import Optional, Any


@dataclass
class TemplateHistoryData:
    # TemplateHistory attributes
    id: str
    name: str
    template_type: str
    created_at: datetime
    updated_at: datetime
    content: str
    service_id: str
    subject: Optional[str]
    postage: Optional[str]
    created_by_id: Optional[Any]
    version: int
    archived: bool
    process_type: Optional[str]
    service_letter_contact_id: Optional[Any]

    # Additional attributes from TemplateBase
    content_as_html: Optional[str] = None
    content_as_plain_text: Optional[str] = None
    hidden: bool = False
    onsite_notification: bool = False
    reply_to_email: Optional[str] = None
    provider_id: Optional[Any] = None
    communication_item_id: Optional[Any] = None
    redact_personalisation: bool = False
    get_reply_to_text: Optional[Any] = None


@transactional
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_create_template(template: Template):
    """Create a new template and associated records.

    This function persists a template to the database, along with:
    - generating a UUID if one isn't provided
    - setting the archived flag to False
    - creating a TemplateRedacted entry with default values
    - generating HTML content for email templates

    A template history record is automatically created via the version_class decorator.

    Args:
        template: The Template object to be created. Should have service, created_by,
                 name, template_type, and content attributes set.

    Returns:
        None - The template parameter is modified in place with generated values.
    """
    template.id = template.id or uuid.uuid4()  # must be set now so version history model can use same id
    template.archived = False

    redacted_dict = {
        'template': template,
        'redact_personalisation': False,
    }
    if template.created_by:
        redacted_dict.update({'updated_by': template.created_by})
    else:
        redacted_dict.update({'updated_by_id': template.created_by_id})

    template.template_redacted = TemplateRedacted(**redacted_dict)
    template.content_as_plain_text = None

    if template.template_type == EMAIL_TYPE and is_feature_enabled(FeatureFlag.STORE_TEMPLATE_CONTENT):
        template.content_as_html = generate_html_email_content(template)
        template.content_as_plain_text = None

    db.session.add(template)


@transactional
@version_class(VersionOptions(Template, history_class=TemplateHistory))
def dao_update_template(template: Template):
    """Update an existing template and create a history record.

    This function:
    - Removes the template from its folder if the template is being archived
    - Regenerates HTML content for email templates if the template is not archived
    - Creates a new template history record via the version_class decorator

    Args:
        template: The Template object to be updated with modified attributes.
                 The template.id must reference an existing template.

    Returns:
        None - The template parameter is updated in place.
    """
    if template.archived:
        template.folder = None
    if template.template_type == EMAIL_TYPE and is_feature_enabled(FeatureFlag.STORE_TEMPLATE_CONTENT):
        template.content_as_html = generate_html_email_content(template)

    db.session.add(template)


@transactional
def dao_update_template_reply_to(
    template_id,
    reply_to,
):
    stmt = (
        update(Template)
        .where(Template.id == template_id)
        .values(
            service_letter_contact_id=reply_to,
            updated_at=datetime.utcnow(),
            version=Template.version + 1,
        )
    )

    db.session.execute(stmt)

    stmt = select(Template).where(Template.id == template_id)
    template = db.session.scalars(stmt).one()

    history = TemplateHistory(
        **{
            'id': template.id,
            'name': template.name,
            'template_type': template.template_type,
            'created_at': template.created_at,
            'updated_at': template.updated_at,
            'content': template.content,
            'service_id': template.service_id,
            'subject': template.subject,
            'postage': template.postage,
            'created_by_id': template.created_by_id,
            'version': template.version,
            'archived': template.archived,
            'process_type': template.process_type,
            'service_letter_contact_id': template.service_letter_contact_id,
        }
    )
    db.session.add(history)
    return template


@transactional
def dao_redact_template(
    template,
    user_id,
):
    template.template_redacted.redact_personalisation = True
    template.template_redacted.updated_at = datetime.utcnow()
    template.template_redacted.updated_by_id = user_id
    db.session.add(template.template_redacted)


def dao_get_template_by_id_and_service_id(
    template_id,
    service_id,
    version=None,
) -> Template:
    if version is None:
        stmt = select(Template).where(
            Template.id == template_id, Template.hidden.is_(False), Template.service_id == service_id
        )
    else:
        stmt = select(TemplateHistory).where(
            TemplateHistory.id == template_id,
            TemplateHistory.hidden.is_(False),
            TemplateHistory.service_id == service_id,
            TemplateHistory.version == version,
        )

    return db.session.scalars(stmt).one()


def dao_get_number_of_templates_by_service_id_and_name(
    service_id,
    template_name,
    version=None,
):
    if version is None:
        stmt = (
            select(func.count())
            .select_from(Template)
            .where(Template.hidden.is_(False), Template.service_id == service_id, Template.name == template_name)
        )
    else:
        stmt = (
            select(func.count())
            .select_from(TemplateHistory)
            .where(
                TemplateHistory.hidden.is_(False),
                TemplateHistory.service_id == service_id,
                TemplateHistory.name == template_name,
                TemplateHistory.version == version,
            )
        )

    return db.session.scalar(stmt)


@cached(cache=TTLCache(maxsize=1024, ttl=600))
def dao_get_template_history_by_id(template_id: str, version: str) -> TemplateHistoryData | None:
    stmt = select(TemplateHistory).where(TemplateHistory.id == template_id, TemplateHistory.version == version)
    template_history_object = db.session.scalars(stmt).first()

    if template_history_object is not None:
        return TemplateHistoryData(
            id=template_history_object.id,
            name=template_history_object.name,
            template_type=template_history_object.template_type,
            created_at=template_history_object.created_at,
            updated_at=template_history_object.updated_at,
            content=template_history_object.content,
            service_id=template_history_object.service_id,
            subject=template_history_object.subject,
            postage=template_history_object.postage,
            created_by_id=template_history_object.created_by_id,
            version=template_history_object.version,
            archived=template_history_object.archived,
            process_type=template_history_object.process_type,
            service_letter_contact_id=template_history_object.service_letter_contact_id,
            content_as_html=template_history_object.content_as_html,
            content_as_plain_text=template_history_object.content_as_plain_text,
            hidden=template_history_object.hidden,
            onsite_notification=template_history_object.onsite_notification,
            reply_to_email=template_history_object.reply_to_email,
            provider_id=template_history_object.provider_id,
            communication_item_id=template_history_object.communication_item_id,
            redact_personalisation=getattr(template_history_object, 'redact_personalisation', False),
            get_reply_to_text=template_history_object.get_reply_to_text,
        )
    return None


def dao_get_template_by_id(
    template_id,
    version=None,
) -> Template | TemplateHistoryData:
    if version is None:
        stmt = select(Template).where(Template.id == template_id)
        return db.session.scalars(stmt).one()
    else:
        template_id_str = str(template_id)
        version_str = str(version)
        return dao_get_template_history_by_id(template_id_str, version_str)


def dao_get_all_templates_for_service(
    service_id,
    template_type=None,
):
    if template_type is None:
        stmt = (
            select(Template)
            .where(Template.service_id == service_id, Template.hidden.is_(False), Template.archived.is_(False))
            .order_by(asc(Template.name), asc(Template.template_type))
        )
    else:
        stmt = (
            select(Template)
            .where(
                Template.service_id == service_id,
                Template.template_type == template_type,
                Template.hidden.is_(False),
                Template.archived.is_(False),
            )
            .order_by(asc(Template.name), asc(Template.template_type))
        )

    return db.session.scalars(stmt).all()


def dao_get_template_versions(
    service_id,
    template_id,
):
    stmt = (
        select(TemplateHistory)
        .where(
            TemplateHistory.service_id == service_id,
            TemplateHistory.id == template_id,
            TemplateHistory.hidden.is_(False),
        )
        .order_by(desc(TemplateHistory.version))
    )

    return db.session.scalars(stmt).all()
