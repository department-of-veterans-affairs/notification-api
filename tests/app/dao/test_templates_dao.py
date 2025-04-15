from datetime import datetime
from typing import Any, Callable, Generator, Literal
from uuid import UUID, uuid4

from freezegun import freeze_time
import pytest
from pytest_mock.plugin import MockerFixture
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app.constants import EMAIL_TYPE, LETTER_TYPE, PINPOINT_PROVIDER, SES_PROVIDER, SMS_TYPE
from app.dao.templates_dao import (
    dao_create_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_update_template,
    dao_get_template_versions,
    dao_redact_template,
    dao_update_template_reply_to,
    dao_get_number_of_templates_by_service_id_and_name,
)
from app.models import (
    ProviderDetails,
    Service,
    ServiceLetterContact,
    Template,
    TemplateFolder,
    TemplateHistory,
    TemplateRedacted,
)
from app.schemas import template_history_schema
from tests.app.db import create_template, create_letter_contact
from tests.app.conftest import template_cleanup


@pytest.mark.parametrize('template_type', [SMS_TYPE, EMAIL_TYPE])
def test_create_only_one_template(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    template_type: Literal['sms'] | Literal['email'],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': template_type,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }

    if template_type == EMAIL_TYPE:
        data.update({'subject': 'subject'})
    template = Template(**data)
    dao_create_template(template)

    persisted_template = notify_db_session.session.get(Template, template.id)
    try:
        assert persisted_template == template
    finally:
        # Teardown because we cannot use a sample here
        template_cleanup(notify_db_session.session, template.id)


@pytest.mark.parametrize(
    'template_type, subject',
    [
        (SMS_TYPE, None),
        (EMAIL_TYPE, 'subject'),
        (LETTER_TYPE, 'subject'),
    ],
)
def test_create_template(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    template_type: Literal['sms'] | Literal['email'] | Literal['letter'],
    subject: None | Literal['subject'],
):
    service = sample_service()

    data = {
        'name': 'Sample Template',
        'template_type': template_type,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }
    if template_type == LETTER_TYPE:
        data['postage'] = 'second'
    if subject:
        data.update({'subject': subject})
    template = Template(**data)
    dao_create_template(template)

    db_template = notify_db_session.session.get(Template, template.id)
    assert db_template == template
    assert len(dao_get_all_templates_for_service(service.id)) == 1
    assert dao_get_all_templates_for_service(service.id)[0].name == 'Sample Template'
    assert dao_get_all_templates_for_service(service.id)[0].process_type == 'normal'

    # Teardown
    template_cleanup(notify_db_session.session, db_template.id)


def test_create_template_creates_redact_entry(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    template = create_template(service)

    redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    assert redacted.template_id == template.id
    assert redacted.redact_personalisation is False
    assert redacted.updated_by_id == service.created_by_id

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_create_template_with_reply_to(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    letter_contact = create_letter_contact(service, 'Edinburgh, ED1 1AA')

    data = {
        'name': 'Sample Template',
        'template_type': LETTER_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'reply_to': letter_contact.id,
        'postage': 'second',
    }
    template = Template(**data)
    dao_create_template(template)

    assert dao_get_all_templates_for_service(service.id)[0].reply_to == letter_contact.id

    # Teardown
    letter_contact = notify_db_session.session.get(ServiceLetterContact, letter_contact.id)
    template_cleanup(notify_db_session.session, template.id)


def test_update_template(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': SMS_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }
    template = Template(**data)
    dao_create_template(template)
    created = dao_get_all_templates_for_service(service.id)[0]
    assert created.name == 'Sample Template'

    created.name = 'new name'
    dao_update_template(created)
    assert dao_get_all_templates_for_service(service.id)[0].name == 'new name'

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_update_template_in_a_folder_to_archived(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    template_data = {
        'name': 'Sample Template',
        'template_type': SMS_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }
    template = Template(**template_data)

    template_folder_data = {
        'name': 'My Folder',
        'service_id': service.id,
    }
    template_folder = TemplateFolder(**template_folder_data)

    template.folder = template_folder
    dao_create_template(template)

    template.archived = True
    dao_update_template(template)

    template_folder = notify_db_session.session.get(TemplateFolder, template_folder.id)
    archived_template = notify_db_session.session.get(Template, template.id)

    assert template_folder
    assert not archived_template.folder

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_dao_update_template_reply_to_none_to_some(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    letter_contact = create_letter_contact(service, 'Edinburgh, ED1 1AA')

    data = {
        'name': 'Sample Template',
        'template_type': LETTER_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'postage': 'second',
    }
    template = Template(**data)
    dao_create_template(template)
    created = notify_db_session.session.get(Template, template.id)

    assert created.reply_to is None
    assert created.service_letter_contact_id is None

    dao_update_template_reply_to(template_id=template.id, reply_to=letter_contact.id)

    updated = notify_db_session.session.get(Template, template.id)
    assert updated.reply_to == letter_contact.id
    assert updated.version == 2
    assert updated.updated_at

    stmt = select(TemplateHistory).where(TemplateHistory.id == created.id).where(TemplateHistory.version == 2)
    template_history = notify_db_session.session.scalars(stmt).one()
    assert template_history.service_letter_contact_id == letter_contact.id
    assert template_history.updated_at == updated.updated_at

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_dao_update_template_reply_to_some_to_some(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    letter_contact = create_letter_contact(service, 'Edinburgh, ED1 1AA')
    letter_contact_2 = create_letter_contact(service, 'London, N1 1DE')

    data = {
        'name': 'Sample Template',
        'template_type': LETTER_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'service_letter_contact_id': letter_contact.id,
        'postage': 'second',
    }
    template = Template(**data)
    dao_create_template(template)

    created = notify_db_session.session.get(Template, template.id)
    dao_update_template_reply_to(template_id=created.id, reply_to=letter_contact_2.id)
    updated = notify_db_session.session.get(Template, template.id)

    assert updated.reply_to == letter_contact_2.id
    assert updated.version == 2
    assert updated.updated_at

    stmt = select(TemplateHistory).where(TemplateHistory.id == created.id).where(TemplateHistory.version == 2)
    updated_history = notify_db_session.session.scalars(stmt).one()
    assert updated_history.service_letter_contact_id == letter_contact_2.id
    assert updated_history.updated_at == updated_history.updated_at

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_dao_update_template_reply_to_some_to_none(
    notify_db_session: Any, sample_service: Callable[..., Any | Service]
):
    service = sample_service()
    letter_contact = create_letter_contact(service, 'Edinburgh, ED1 1AA')
    data = {
        'name': 'Sample Template',
        'template_type': LETTER_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'service_letter_contact_id': letter_contact.id,
        'postage': 'second',
    }
    template = Template(**data)
    dao_create_template(template)
    created = notify_db_session.session.get(Template, template.id)
    dao_update_template_reply_to(template_id=created.id, reply_to=None)
    updated = notify_db_session.session.get(Template, template.id)
    assert updated.reply_to is None
    assert updated.version == 2
    assert updated.updated_at

    stmt = select(TemplateHistory).where(TemplateHistory.id == created.id).where(TemplateHistory.version == 2)
    history = notify_db_session.session.scalars(stmt).one()
    assert history.service_letter_contact_id is None
    assert history.updated_at == updated.updated_at

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_redact_template(
    notify_db_session: Any,
    sample_template: Callable[..., Any],
):
    template = sample_template()
    redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    assert redacted.template_id == template.id
    assert redacted.redact_personalisation is False

    time = datetime.now()
    with freeze_time(time):
        dao_redact_template(template, template.created_by_id)

    assert redacted.redact_personalisation is True
    assert redacted.updated_at == time
    assert redacted.updated_by_id == template.created_by_id


def test_get_all_templates_for_service(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
):
    service_0 = sample_service()
    service_1 = sample_service()

    sample_template(service=service_0)
    sample_template(service=service_1)

    assert len(dao_get_all_templates_for_service(service_0.id)) == 1
    assert len(dao_get_all_templates_for_service(service_1.id)) == 1

    templates = []
    templates.append(
        create_template(
            service=service_0,
            template_name='Sample Template 1',
            template_type=SMS_TYPE,
            content='Template content',
        )
    )
    templates.append(
        create_template(
            service=service_0,
            template_name='Sample Template 2',
            template_type=SMS_TYPE,
            content='Template content',
        )
    )
    templates.append(
        create_template(
            service=service_1,
            template_name='Sample Template 3',
            template_type=SMS_TYPE,
            content='Template content',
        )
    )

    assert len(dao_get_all_templates_for_service(service_0.id)) == 3
    assert len(dao_get_all_templates_for_service(service_1.id)) == 2

    # Teardown
    for template in templates:
        template_cleanup(notify_db_session.session, template.id)


def test_get_all_templates_for_service_is_alphabetised(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    """
    Tests that templates appear in order and a rename of one of them yields the updates list ordering.
    """

    service = sample_service()
    templates = []

    templates.append(
        create_template(
            template_name=f'100_{uuid4()}',
            template_type=SMS_TYPE,
            content='Template content',
            service=service,
        )
    )
    template_2 = create_template(
        template_name=f'200_{uuid4()}', template_type=SMS_TYPE, content='Template content', service=service
    )
    templates.append(template_2)
    templates.append(
        create_template(
            template_name=f'300_{uuid4()}', template_type=SMS_TYPE, content='Template content', service=service
        )
    )

    templates_for_service = dao_get_all_templates_for_service(service.id)
    assert templates_for_service[0].name == templates[0].name
    assert templates_for_service[1].name == templates[1].name
    assert templates_for_service[2].name == templates[2].name

    # Make it so template_2 appears before template_1
    rename_template_2 = template_2.name.replace('200_', '000_')
    template_2.name = rename_template_2
    dao_update_template(template_2)

    templates_for_service = dao_get_all_templates_for_service(service.id)
    assert templates_for_service[0].name == templates[1].name
    assert templates_for_service[1].name == templates[0].name

    # Teardown
    for template in templates:
        template_cleanup(notify_db_session.session, template.id)


def test_get_all_returns_empty_list_if_no_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    assert notify_db_session.session.scalar(select(Template).where(Template.service_id == service.id)) is None
    assert len(dao_get_all_templates_for_service(service.id)) == 0


def test_get_all_templates_ignores_archived_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    normal_template = create_template(template_name=str(uuid4()), service=service, archived=False)
    archived_template = create_template(template_name=str(uuid4()), service=service)

    # sample_template fixture uses dao, which forces archived = False at creation.
    archived_template.archived = True
    dao_update_template(archived_template)

    templates = dao_get_all_templates_for_service(service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template

    # Teardown
    template_cleanup(notify_db_session.session, normal_template.id)
    template_cleanup(notify_db_session.session, archived_template.id)


def test_get_all_templates_ignores_hidden_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    normal_template = create_template(template_name=str(uuid4()), service=service, archived=False)

    hidden_template = create_template(template_name=str(uuid4()), hidden=True, service=service)

    templates = dao_get_all_templates_for_service(service.id)

    assert len(templates) == 1
    assert templates[0] == normal_template

    # Teardown
    template_cleanup(notify_db_session.session, normal_template.id)
    template_cleanup(notify_db_session.session, hidden_template.id)


def test_get_template_by_id_and_service(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    original_name = str(uuid4())
    template_0 = create_template(template_name=original_name, service=service)
    template_1 = dao_get_template_by_id_and_service_id(template_id=template_0.id, service_id=service.id)

    assert template_1.id == template_0.id
    assert template_1.name == original_name
    assert template_1.version == template_0.version
    assert not template_1.redact_personalisation

    # Teardown
    template_cleanup(notify_db_session.session, template_0.id)


def test_get_template_by_id_and_service_returns_none_for_hidden_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    template = create_template(template_name='Test Template', hidden=True, service=service)

    with pytest.raises(NoResultFound):
        dao_get_template_by_id_and_service_id(template_id=template.id, service_id=service.id)

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_get_template_version_returns_none_for_hidden_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    template = create_template(template_name='Test Template', hidden=True, service=service)

    with pytest.raises(NoResultFound):
        dao_get_template_by_id_and_service_id(template.id, service.id, '1')

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_get_template_by_id_and_service_returns_none_if_no_template(
    sample_service: Callable[..., Any | Service],
    fake_uuid_v2: UUID,
):
    with pytest.raises(NoResultFound) as e:
        dao_get_template_by_id_and_service_id(template_id=fake_uuid_v2, service_id=sample_service().id)
    assert 'No row was found when one' in str(e.value)


def test_create_template_creates_a_history_record_with_current_data(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()

    data = {
        'name': 'Sample Template',
        'template_type': EMAIL_TYPE,
        'subject': 'subject',
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }
    template = Template(**data)
    dao_create_template(template)

    template_from_db = notify_db_session.session.get(Template, template.id)
    template_history = notify_db_session.session.get(TemplateHistory, (template.id, template.version))

    assert template_from_db.id == template_history.id
    assert template_from_db.name == template_history.name
    assert template_from_db.version == 1
    assert template_from_db.version == template_history.version
    assert service.created_by_id == template_history.created_by_id
    assert template_from_db.created_by.id == template_history.created_by_id

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_update_template_creates_a_history_record_with_current_data(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': EMAIL_TYPE,
        'subject': 'subject',
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }
    template = Template(**data)
    dao_create_template(template)

    created = dao_get_all_templates_for_service(service.id)[0]
    assert created.name == data['name']

    # Use the found template
    db_template = notify_db_session.session.get(Template, created.id)
    assert db_template
    assert db_template.version == 1
    assert notify_db_session.session.get(TemplateHistory, (created.id, created.version))

    created.name = 'new name'
    dao_update_template(created)

    template_from_db = notify_db_session.session.get(Template, created.id)
    assert template_from_db
    assert notify_db_session.session.get(TemplateHistory, (template.id, template.version))
    assert template_from_db.version == 2

    stmt = select(TemplateHistory).where(TemplateHistory.name == data['name']).where(TemplateHistory.version == 1)
    hist_original = notify_db_session.session.scalar(stmt)
    assert hist_original

    stmt = select(TemplateHistory).where(TemplateHistory.name == 'new name').where(TemplateHistory.version == 2)
    hist_update = notify_db_session.session.scalar(stmt)
    assert hist_update

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_get_template_history_version(
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
):
    service = sample_service()
    template = sample_template(service=service)
    old_content = template.content
    template.content = 'New content'

    dao_update_template(template)
    old_template = dao_get_template_by_id_and_service_id(template.id, service.id, '1')

    assert old_template.content == old_content


def test_can_get_template_then_redacted_returns_right_values(
    sample_template: Callable[..., Any],
):
    template = sample_template()
    dao_template = dao_get_template_by_id_and_service_id(
        template_id=template.id,
        service_id=template.service_id,
    )

    assert not dao_template.redact_personalisation
    dao_redact_template(template=dao_template, user_id=template.created_by_id)
    assert dao_template.redact_personalisation


def test_can_get_template_by_service_id_and_name(
    sample_template: Callable[..., Any],
):
    template = sample_template()
    num_templates = dao_get_number_of_templates_by_service_id_and_name(
        service_id=template.service_id, template_name=template.name
    )

    assert num_templates == 1


def test_does_not_find_template_by_service_id_and_invalid_name(
    sample_template: Callable[..., Any],
):
    num_templates = dao_get_number_of_templates_by_service_id_and_name(
        service_id=sample_template().service_id, template_name='some random template name'
    )

    assert num_templates == 0


def test_get_template_versions(
    sample_template: Callable[..., Any],
):
    template = sample_template()
    original_content = template.content
    template.content = 'new version'
    dao_update_template(template)
    versions = dao_get_template_versions(service_id=template.service_id, template_id=template.id)
    assert len(versions) == 2
    versions = sorted(versions, key=lambda x: x.version)
    assert versions[0].content == original_content
    assert versions[1].content == 'new version'

    assert versions[0].created_at == versions[1].created_at

    assert versions[0].updated_at is None
    assert versions[1].updated_at is not None

    v = template_history_schema.dump(versions, many=True)
    assert len(v) == 2


def test_get_template_versions_is_empty_for_hidden_templates(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    template = create_template(
        template_name='Test Template',
        hidden=True,
        service=sample_service(),
    )
    versions = dao_get_template_versions(service_id=template.service_id, template_id=template.id)
    assert len(versions) == 0

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


@pytest.mark.parametrize('template_type,postage', [(LETTER_TYPE, 'third'), (SMS_TYPE, 'second')])
def test_template_postage_constraint_on_create(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    template_type: Literal['letter'] | Literal['sms'],
    postage: Literal['third'] | Literal['second'],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': template_type,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'postage': postage,
    }
    template = Template(**data)
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_create_template(template)

    stmt = select(Template).where(Template.service_id == service.id)
    assert len(notify_db_session.session.scalars(stmt).all()) == 0


def test_template_postage_constraint_on_update(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': LETTER_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'postage': 'second',
    }
    template = Template(**data)
    dao_create_template(template)

    created = dao_get_all_templates_for_service(service.id)[0]
    assert created.name == data['name']

    created.postage = 'third'
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_update_template(created)

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_template_with_no_given_provider_id_has_null_provider_id(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    data = {
        'name': 'Sample Template',
        'template_type': EMAIL_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
    }

    template = Template(**data)
    dao_create_template(template)

    assert notify_db_session.session.get(Template, template.id).provider_id is None

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


@pytest.mark.parametrize('identifier,notification_type', [(SES_PROVIDER, EMAIL_TYPE), (PINPOINT_PROVIDER, SMS_TYPE)])
def test_template_with_provider_id_persists_provider_id(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    sample_provider: Callable[..., Any | ProviderDetails],
    identifier: Literal['ses'] | Literal['pinpoint'],
    notification_type: Literal['email'] | Literal['sms'],
):
    service = sample_service()
    provider = sample_provider(identifier=identifier, notification_type=notification_type)
    data = {
        'name': str(uuid4()),
        'template_type': EMAIL_TYPE,
        'content': 'Template content',
        'service': service,
        'created_by': service.created_by,
        'provider_id': provider.id,
    }

    template = Template(**data)
    dao_create_template(template)

    assert notify_db_session.session.get(Template, template.id).provider_id == provider.id
    # Teardown
    template_cleanup(notify_db_session.session, template.id)


@pytest.mark.parametrize(
    'template_type, feature_flag_enabled, expected_html',
    [
        (SMS_TYPE, True, False),  # SMS templates never have HTML content
        (SMS_TYPE, False, False),  # SMS templates never have HTML content
        (EMAIL_TYPE, True, True),  # Email templates have HTML content when flag is enabled
        (EMAIL_TYPE, False, False),  # Email templates don't have HTML content when flag is disabled
    ],
)
def test_dao_create_template_sets_content_as_html_correctly(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    template_type: Literal['sms'] | Literal['email'],
    feature_flag_enabled: bool,
    expected_html: bool,
    mocker: Callable[..., Generator[MockerFixture, None, None]],
):
    # Mock the feature flag
    mocker.patch('app.feature_flags.is_feature_enabled', return_value=feature_flag_enabled)

    service = sample_service()
    data = {
        'name': f'Sample Template {str(uuid4())}',
        'template_type': template_type,
        'content': 'Template <em>content</em> with <strong>formatting</strong>',
        'service': service,
        'created_by': service.created_by,
    }

    if template_type == EMAIL_TYPE:
        data['subject'] = 'Email Subject'

    template = Template(**data)
    dao_create_template(template)

    persisted_template = notify_db_session.session.get(Template, template.id)

    try:
        if expected_html:
            assert persisted_template.content_as_html is not None
            assert 'Template <em>content</em> with <strong>formatting</strong>' in persisted_template.content_as_html
        else:
            assert persisted_template.content_as_html is None
    finally:
        # Teardown
        template_cleanup(notify_db_session.session, template.id)


@pytest.mark.parametrize(
    'template_type, feature_flag_enabled, expected_html',
    [
        (SMS_TYPE, True, False),  # SMS templates never have HTML content
        (SMS_TYPE, False, False),  # SMS templates never have HTML content
        (EMAIL_TYPE, True, True),  # Email templates have HTML content when flag is enabled
        (EMAIL_TYPE, False, False),  # Email templates don't have HTML content when flag is disabled
    ],
)
def test_dao_update_template_updates_content_as_html_correctly(
    notify_db_session: Any,
    sample_service: Callable[..., Any | Service],
    template_type: Literal['sms'] | Literal['email'],
    feature_flag_enabled: bool,
    expected_html: bool,
    mocker: Callable[..., Generator[MockerFixture, None, None]],
):
    # Mock the feature flag
    mocker.patch('app.feature_flags.is_feature_enabled', return_value=feature_flag_enabled)

    service = sample_service()
    template_name = f'Sample Template {str(uuid4())}'

    # Create initial template
    template = create_template(
        service=service,
        template_name=template_name,
        template_type=template_type,
        content='Initial template content',
        subject='Email Subject' if template_type == EMAIL_TYPE else None,
    )

    # Refresh session to ensure clean state
    notify_db_session.session.expire_all()

    # Fetch the template
    template = dao_get_template_by_id_and_service_id(template.id, service.id)

    # Update template with new content including HTML formatting
    template.content = 'Updated <em>content</em> with <strong>formatting</strong>'
    dao_update_template(template)

    # Get the updated template from the database
    updated_template = notify_db_session.session.get(Template, template.id)

    try:
        # Verify content_as_html is updated correctly based on feature flag
        if expected_html:
            assert updated_template.content_as_html is not None
            assert 'Updated <em>content</em> with <strong>formatting</strong>' in updated_template.content_as_html
        else:
            assert updated_template.content_as_html is None

        # Also verify history was created properly
        template_history = notify_db_session.session.scalars(
            select(TemplateHistory).where(TemplateHistory.id == template.id).where(TemplateHistory.version == 2)
        ).first()

        assert template_history is not None
        assert template_history.content == 'Updated <em>content</em> with <strong>formatting</strong>'
    finally:
        # Teardown
        template_cleanup(notify_db_session.session, template.id)


def test_template_html_property_getter_with_content_as_html(
    notify_db_session: Any, sample_template: Callable[..., Any]
):
    """Test that the html property returns content_as_html if it exists."""
    html_content = '<h1>Hello World</h1><p>This is an email.</p>'

    # Create a template with content_as_html already set
    template = sample_template(template_type=EMAIL_TYPE)
    template.content_as_html = html_content
    notify_db_session.session.commit()

    # Test that the html property returns the content_as_html
    assert template.html == html_content


def test_template_html_property_getter_for_email_without_content_as_html(
    notify_db_session: Any, sample_template: Callable[..., Any], mocker: MockerFixture
):
    """Test that the html property generates HTML for email templates when content_as_html is None."""
    # Create an email template without content_as_html
    template = sample_template(
        template_type=EMAIL_TYPE, content='Hello ((name)). This is an email with **bold** text.', subject='Test Subject'
    )
    template.content_as_html = None
    notify_db_session.session.commit()

    # Test that the html property generates HTML for email templates
    assert template.html is not None
    assert 'Hello ((name))' in template.html
    assert '<b>bold</b>' in template.html


def test_template_html_property_getter_for_sms_returns_none(
    notify_db_session: Any, sample_template: Callable[..., Any]
):
    """Test that the html property returns None for SMS templates."""
    # Create an SMS template
    template = sample_template(template_type=SMS_TYPE, content='Hello. This is an SMS.')
    template.content_as_html = None
    notify_db_session.session.commit()

    # Test that the html property returns None for SMS templates
    assert template.html is None


def test_template_html_property_setter_with_value(notify_db_session: Any, sample_template: Callable[..., Any]):
    """Test that the html setter sets content_as_html when a value is provided."""
    html_content = '<h1>Custom HTML</h1><p>This is custom HTML content.</p>'

    # Create a template
    template = sample_template(template_type=EMAIL_TYPE, content='Hello. This is an email.', subject='Test Subject')

    # Set the html property with a value
    template.html = html_content
    notify_db_session.session.commit()

    # Refresh the template from the database
    notify_db_session.session.refresh(template)

    # Test that content_as_html is set to the provided value
    assert template.content_as_html == html_content
    assert template.html == html_content


def test_template_html_property_setter_without_value(
    notify_db_session: Any, sample_template: Callable[..., Any], mocker: MockerFixture
):
    """Test that the html setter generates content_as_html using generate_html_email_content when no value is provided."""
    # Mock the generate_html_email_content function
    mock_generate_html = mocker.patch('app.models.generate_html_email_content', return_value='<h1>Generated HTML</h1>')

    # Create a template
    template = sample_template(template_type=EMAIL_TYPE, content='Hello. This is an email.', subject='Test Subject')

    # Set the html property without a value
    template.html = None
    notify_db_session.session.commit()

    # Refresh the template from the database
    notify_db_session.session.refresh(template)

    # Test that generate_html_email_content was called with the template
    mock_generate_html.assert_called_once_with(template)

    # Test that content_as_html is set to the generated value
    assert template.content_as_html == '<h1>Generated HTML</h1>'
