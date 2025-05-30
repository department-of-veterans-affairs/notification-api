from datetime import datetime
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from freezegun import freeze_time
import pytest
from pytest_mock.plugin import MockerFixture
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app.constants import EMAIL_TYPE, LETTER_TYPE, PINPOINT_PROVIDER, SES_PROVIDER, SMS_TYPE
from app.dao.templates_dao import (
    TemplateHistoryData,
    dao_create_template,
    dao_get_template_by_id,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_update_template,
    dao_get_template_versions,
    dao_redact_template,
    dao_update_template_reply_to,
    dao_get_number_of_templates_by_service_id_and_name,
)
from app.db import SQLAlchemy
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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


def test_create_email_template_with_html_enabled(
    notify_db_session: SQLAlchemy,
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
):
    """Test creating an email template with HTML content generation enabled."""
    # Mock generate_html_email_content to return a fixed string for testing
    mock_html_content = '<p>Template with HTML content</p>'
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=mock_html_content,
    )
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=True)

    template = sample_template(
        template_type=EMAIL_TYPE,
        content='Template with content',
    )

    mock_generate.assert_called_once_with(template)
    assert template.content_as_html == mock_html_content


def test_create_email_template_with_html_disabled(
    notify_db_session: SQLAlchemy,
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
):
    """Test creating an email template with HTML content generation disabled."""
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=None,
    )
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=False)

    template = sample_template(
        template_type=EMAIL_TYPE,
        content='Template with content',
    )
    persisted_template = notify_db_session.session.get(Template, template.id)
    # Assert generate_html_email_content was called but HTML content is not set
    mock_generate.assert_not_called()
    assert persisted_template.content_as_html is None


@pytest.mark.parametrize('feature_enabled', [True, False])
def test_create_sms_template_content_as_html_always_none(
    notify_db_session: SQLAlchemy,
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
    feature_enabled: bool,
):
    """Test creating an SMS template always has content_as_html set to None regardless of feature flag status."""
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=None,
    )
    # Set feature flag based on parameter
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=feature_enabled)

    template = sample_template(
        template_type=SMS_TYPE,
        content='Template with content',
    )
    # Assert generate_html_email_content was called but HTML content is not set for SMS
    mock_generate.assert_not_called()
    assert template.content_as_html is None


def test_update_email_template_updates_content_as_html(
    notify_db_session: SQLAlchemy,
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
):
    # Mock generate_html_email_content to return a fixed string for testing
    mock_html_content = '<p>Updated HTML content</p>'
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=mock_html_content,
    )
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=True)
    template = sample_template(template_type=EMAIL_TYPE)

    # Update the template content
    template.content = 'Updated content'
    dao_update_template(template)
    updated_template = notify_db_session.session.get(Template, template.id)

    # Assert generate_html_email_content was called appropriately
    mock_generate.assert_called_with(template)
    assert updated_template.content_as_html == mock_html_content


def test_update_email_template_without_html_feature(
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
):
    # Mock generate_html_email_content to return None when feature is disabled
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=None,
    )
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=False)
    template = sample_template(template_type=EMAIL_TYPE)

    # Update the template content
    template.content = 'Updated content'
    dao_update_template(template)
    updated_template = notify_db_session.session.get(Template, template.id)

    try:
        # Assert generate_html_email_content was called appropriately
        mock_generate.assert_not_called()
        assert updated_template.content_as_html is None
    finally:
        template_cleanup(notify_db_session.session, template.id)


def test_update_sms_template_does_not_update_html_content(
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
    mocker: MockerFixture,
):
    # Mock generate_html_email_content to verify it's called but returns None for SMS
    mock_generate = mocker.patch(
        'app.dao.templates_dao.generate_html_email_content',
        return_value=None,
    )
    mocker.patch('app.dao.templates_dao.is_feature_enabled', return_value=True)
    template = sample_template(template_type=SMS_TYPE)

    # Update the template content
    template.content = 'Updated content'
    dao_update_template(template)
    updated_template = notify_db_session.session.get(Template, template.id)

    try:
        # Assert generate_html_email_content was called but HTML content is None for SMS
        mock_generate.assert_not_called()
        assert updated_template.content_as_html is None
    finally:
        template_cleanup(notify_db_session.session, template.id)


def test_create_template_creates_redact_entry(
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
):
    service = sample_service()

    template_folder_data = {
        'name': 'My Folder',
        'service_id': service.id,
    }
    template_folder = TemplateFolder(**template_folder_data)

    # Create template with folder
    template = sample_template(service=service, folder=template_folder)

    # Verify initial state
    assert template.folder == template_folder

    # Archive the template
    template.archived = True
    dao_update_template(template)

    # Verify template folder still exists but template no longer has folder relationship
    template_folder = notify_db_session.session.get(TemplateFolder, template_folder.id)
    archived_template = notify_db_session.session.get(Template, template.id)

    assert template_folder
    assert not archived_template.folder


def test_dao_update_template_reply_to_none_to_some(
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy, sample_service: Callable[..., Any | Service]
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
):
    template = sample_template()  # This creates a template with a service

    # Create a different service with no templates
    service_with_no_templates = sample_service()

    try:
        # Verify the service with templates has at least one template
        assert len(dao_get_all_templates_for_service(template.service_id)) > 0

        # Verify the service with no templates returns an empty list
        assert (
            notify_db_session.session.scalar(
                select(Template).where(Template.service_id == service_with_no_templates.id)
            )
            is None
        )
        assert len(dao_get_all_templates_for_service(service_with_no_templates.id)) == 0
    finally:
        # Teardown
        template_cleanup(notify_db_session.session, template.id)


def test_get_all_templates_ignores_archived_templates(
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
    sample_template: Callable[..., Any],
):
    service = sample_service()
    normal_template = sample_template(service=service)
    archived_template = sample_template(service=service)

    # sample_template fixture uses dao, which forces archived = False at creation.
    archived_template.archived = True
    dao_update_template(archived_template)

    templates = dao_get_all_templates_for_service(service.id)

    try:
        assert len(templates) == 1
        assert templates[0] == normal_template

    finally:
        # Teardown
        template_cleanup(notify_db_session.session, normal_template.id)
        template_cleanup(notify_db_session.session, archived_template.id)


def test_get_all_templates_ignores_hidden_templates(
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
    sample_service: Callable[..., Any | Service],
):
    service = sample_service()
    template = create_template(template_name='Test Template', hidden=True, service=service)

    with pytest.raises(NoResultFound):
        dao_get_template_by_id_and_service_id(template_id=template.id, service_id=service.id)

    # Teardown
    template_cleanup(notify_db_session.session, template.id)


def test_get_template_version_returns_none_for_hidden_templates(
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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
    notify_db_session: SQLAlchemy,
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


class TestDAOGetTemplateById:
    def test_dao_get_template_by_id_with_no_version(
        self,
        sample_template: Callable[..., Any],
    ):
        template = sample_template()

        result = dao_get_template_by_id(template.id)

        assert result == template

    def test_dao_get_template_by_id_with_specific_version(
        self,
        sample_template: Callable[..., Any],
    ):
        template = sample_template()

        template.content = 'Updated content'
        # This method has a @version_class which created another version in TemplatesHistory.
        dao_update_template(template)

        result = dao_get_template_by_id(template.id, version=1)

        assert isinstance(result, TemplateHistoryData)
        assert result.id == template.id
        assert result.version == 1
        assert result.content != 'Updated content'

    def test_dao_get_template_by_id_with_invalid_version_returns_none(
        self,
        sample_template: Callable[..., Any],
    ):
        template = sample_template()

        result = dao_get_template_by_id(template.id, version=99)

        assert result is None

    def test_dao_get_template_by_id_caching_behavior(
        self,
        notify_db_session: SQLAlchemy,
        sample_template: Callable[..., Any],
        mocker: MockerFixture,
    ):
        # Mock the cache to verify it's being used
        db_spy = mocker.spy(notify_db_session.session, 'scalars')

        template = sample_template()

        # First call - should hit the database
        result1 = dao_get_template_by_id(template.id, version=1)
        assert db_spy.call_count == 1

        # Second call - should use cached result, db call count does not increase
        result2 = dao_get_template_by_id(template.id, version=1)
        assert db_spy.call_count == 1

        assert result1.id == result2.id
