import json
import os
import pytest
import pytz
import requests_mock
from typing import List, Union
from uuid import UUID, uuid4
import warnings
from app import db
from app.clients.email import EmailClient
from app.clients.sms import SmsClient
from app.clients.sms.firetext import FiretextClient
from app.dao.invited_user_dao import save_invited_user
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import dao_create_notification
from app.dao.organisation_dao import dao_create_organisation
from app.dao.permissions_dao import default_service_permissions
from app.dao.provider_rates_dao import create_provider_rates
from app.dao.services_dao import dao_archive_service, dao_create_service, DEFAULT_SERVICE_PERMISSIONS
from app.dao.service_sms_sender_dao import (
    dao_add_sms_sender_for_service,
    dao_update_service_sms_sender,
)
from app.dao.users_dao import create_secret_code, create_user_code
from app.dao.fido2_key_dao import save_fido2_key
from app.dao.login_event_dao import save_login_event
from app.dao.templates_dao import dao_create_template
from app.history_meta import create_history
from app.model import User
from app.models import (
    ApiKey,
    AnnualBilling,
    COMPLAINT_CALLBACK_TYPE,
    CommunicationItem,
    Domain,
    EMAIL_TYPE,
    FactBilling,
    Fido2Key,
    InboundNumber,
    InboundSms,
    InvitedUser,
    Job,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    LETTER_TYPE,
    LoginEvent,
    NORMAL,
    Notification,
    NotificationHistory,
    Organisation,
    Permission,
    PINPOINT_PROVIDER,
    PROVIDERS,
    ProviderDetails,
    ProviderDetailsHistory,
    ProviderRates,
    SMS_TYPE,
    ScheduledNotification,
    SERVICE_PERMISSION_TYPES,
    ServiceCallback,
    ServiceEmailReplyTo,
    ServiceLetterContact,
    ServicePermission,
    ServiceSmsSender,
    Service,
    ServiceUser,
    Template,
    TemplateFolder,
    TemplateHistory,
    TemplateRedacted,
    user_folder_permissions,
    UserServiceRoles,
    WEBHOOK_CHANNEL_TYPE,
)
from app.service.service_data import ServiceData
from datetime import datetime, timedelta
from flask import current_app, url_for
from random import randint, randrange
from sqlalchemy import asc, delete, inspect, update, select, Table
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm.session import make_transient
from tests import create_admin_authorization_header
from tests.app.db import (
    create_api_key,
    create_inbound_number,
    create_invited_org_user,
    create_job,
    create_letter_contact,
    create_notification,
    create_service,
    create_template,
    create_user,
    version_api_key,
    version_service,
)
from tests.app.factories import (
    service_whitelist
)

# Tests only run against email/sms. API also considers letters
TEMPLATE_TYPES = [SMS_TYPE, EMAIL_TYPE]


@pytest.yield_fixture
def rmock():
    with requests_mock.mock() as rmock:
        yield rmock


@pytest.fixture(scope='function')
def service_factory(notify_db_session):
    class ServiceFactory(object):
        def get(self, service_name, user=None, template_type=None, email_from=None):
            if not user:
                user = create_user()
            if not email_from:
                email_from = service_name

            service = create_service(
                email_from=email_from,
                service_name=service_name,
                service_permissions=None,
                user=user,
                check_if_service_exists=True,
            )
            if template_type == EMAIL_TYPE:
                create_template(
                    service,
                    template_name="Template Name",
                    template_type=template_type,
                    subject=service.email_from,
                )
            else:
                create_template(
                    service,
                    template_name="Template Name",
                    template_type='sms',
                )
            return service

    return ServiceFactory()


@pytest.fixture
def set_user_as_admin(notify_db_session):
    def _wrapper(user: User) -> User:
        stmt = update(User).where(User.id == user.id).values(platform_admin=True)
        notify_db_session.session.execute(stmt)
        return notify_db_session.session.get(User, user.id)
    return _wrapper


@pytest.fixture
def sample_user(notify_db_session, set_user_as_admin, worker_id) -> User:
    created_user_ids = {worker_id: []}

    def _sample_user(*args, platform_admin=False, **kwargs):
        # Cannot set platform admin when creating a user (schema)
        user = create_user(*args, **kwargs)
        if platform_admin:
            user = set_user_as_admin(user)

        if worker_id in created_user_ids:
            created_user_ids[worker_id].append(user.id)
        else:
            created_user_ids[worker_id] = [user.id]
        return user

    yield _sample_user

    cleanup_user(created_user_ids, worker_id, notify_db_session.session)


def cleanup_user(user_ids: List[int], worker_id: int, session: scoped_session):
    # Unsafe to teardown with objects, have to use ids to look up the object
    for user_id in user_ids[worker_id]:
        user = session.get(User, user_id)
        # Clear user_folder_permissions
        session.execute(
            delete(user_folder_permissions).where(user_folder_permissions.c.user_id == user.id)
        )

        # Clear permissions
        for user_perm in session.scalars(select(Permission).where(Permission.user_id == user.id)).all():
            session.delete(user_perm)

        # Clear user_to_service
        for user_service in session.scalars(select(ServiceUser).where(ServiceUser.user_id == user.id)).all():
            session.delete(user_service)

        # Clear services created by this user
        stmt = select(Service).where(Service.created_by_id == user_id)
        services = session.scalars(stmt).all()
        if services is not None:
            service_ids = [s.id for s in services]
            service_cleanup(service_ids, session)

        # Delete the user
        session.delete(user)
    session.commit()


@pytest.fixture
def sample_service_callback(notify_db_session, sample_service):
    service_callback_ids = []

    def _wrapper(
            service_id=None,
            url='',
            bearer_token="some_super_secret",
            updated_by_id=None,
            callback_type=COMPLAINT_CALLBACK_TYPE,
            callback_channel=WEBHOOK_CHANNEL_TYPE):
        data = {
            'service_id': service_id,
            'url': url or f"https://something{uuid4()}.com",
            'bearer_token': bearer_token,
            'updated_by_id': updated_by_id,
            'callback_type': callback_type,
            'callback_channel': callback_channel,
        }
        service = None

        if service_id is None or updated_by_id is None:
            service = sample_service()
            # Input may have a different service for each. Only update if it did not set it
            if service_id is None:
                data['service_id'] = str(service.id)
            if updated_by_id is None:
                data['updated_by_id'] = str(service.users[0].id)

        service_callback = ServiceCallback(**data)
        notify_db_session.session.add(service_callback)
        notify_db_session.session.commit()
        service_callback_ids.append(service_callback.id)

        return service_callback

    yield _wrapper

    # Teardown
    for sc_id in service_callback_ids:
        service_callback = notify_db_session.session.get(ServiceCallback, sc_id)
        if service_callback is None:
            continue

        notify_db_session.session.delete(service_callback)
    notify_db_session.session.commit()


@pytest.fixture(scope='function')
def sample_user_service_role(notify_db_session, sample_service):
    service = sample_service()
    user_service_role = UserServiceRoles(
        user_id=service.users[0].id,
        service_id=service.id,
        role="admin",
        created_at=datetime.utcnow(),
    )

    yield user_service_role


@pytest.fixture(scope='function')
def sample_service_role_udpated(notify_db_session, sample_service):
    service = sample_service()
    user_service_role = UserServiceRoles(
        user_id=service.users[0].id,
        service_id=sample_service().id,
        role="admin",
        created_at=datetime_in_past(days=3),
        updated_at=datetime.utcnow(),
    )

    yield user_service_role


@pytest.fixture(scope="function")
def notify_user(notify_db_session, worker_id):
    new_user = create_user(
        email=f"notify-service-user-{worker_id}@digital.cabinet-office.gov.uk",
        id_=current_app.config["NOTIFY_USER_ID"]
    )

    yield new_user

    notify_db_session.session.delete(new_user)
    notify_db_session.session.commit()


@pytest.fixture
def sample_domain(notify_db_session):
    domains = []

    def _wrapper(domain, organisation_id):
        domain = Domain(domain=domain, organisation_id=organisation_id)

        db.session.add(domain)
        db.session.commit()
        domains.append(domain)
        return domain

    yield _wrapper

    # Teardown
    for domain in domains:
        notify_db_session.session.delete(domain)
    notify_db_session.session.commit()


def create_code(notify_db_session, code_type, usr=None, code=None):
    if code is None:
        code = create_secret_code()
    if usr is None:
        usr = create_user()
    return create_user_code(usr, code, code_type), code


@pytest.fixture(scope='function')
def sample_email_code(notify_db,
                      notify_db_session,
                      code=None,
                      code_type="email",
                      usr=None):
    code, txt_code = create_code(notify_db,
                                 notify_db_session,
                                 code_type,
                                 usr=usr,
                                 code=code)
    code.txt_code = txt_code
    return code


@pytest.fixture(scope='function')
def sample_sms_code(notify_db,
                    notify_db_session,
                    code=None,
                    code_type="sms",
                    usr=None):
    code, txt_code = create_code(notify_db,
                                 notify_db_session,
                                 code_type,
                                 usr=usr,
                                 code=code)
    code.txt_code = txt_code
    return code


def create_user_model(
        mobile_number="+16502532222",
        email="notify@notify.va.gov",
        state='active',
        id_=None,
        name="Test User",
        blocked=False,
):
    data = {
        'id': id_ or uuid4(),
        'name': name,
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': state,
        'blocked': blocked
    }
    user = User(**data)
    return user


def create_service_model(
        user=None,
        service_name="Test service",
        restricted=False,
        count_as_live=True,
        research_mode=False,
        active=True,
        email_from=None,
        prefix_sms=True,
        message_limit=1000,
        organisation_type='other',
        go_live_user=None,
        go_live_at=None,
        crown=True,
        organisation=None,
        smtp_user=None
) -> Service:
    service = Service(
        name=service_name,
        message_limit=message_limit,
        restricted=restricted,
        email_from=email_from if email_from else service_name.lower().replace(' ', '.'),
        created_by=user if user else create_user_model(),
        prefix_sms=prefix_sms,
        organisation_type=organisation_type,
        go_live_user=go_live_user,
        go_live_at=go_live_at,
        crown=crown,
        smtp_user=smtp_user,
        organisation=organisation if organisation else Organisation(id=uuid4(), name='sample organization')
    )
    service.active = active
    service.research_mode = research_mode
    service.count_as_live = count_as_live

    return service


def create_template_model(
        service,
        template_type=EMAIL_TYPE,
        template_name=None,
        subject='Template subject',
        content='Dear Sir/Madam, Hello. Yours Truly, The Government.',
        reply_to=None,
        hidden=False,
        folder=None,
        process_type='normal',
):
    data = {
        'id': uuid4(),
        'name': template_name or '{} Template Name'.format(template_type),
        'template_type': template_type,
        'content': content,
        'service': service,
        'created_by': service.created_by,
        'reply_to': reply_to,
        'hidden': hidden,
        'folder': folder,
        'process_type': process_type
    }
    if template_type != SMS_TYPE:
        data['subject'] = subject
    template = Template(**data)

    return template


@pytest.fixture(scope='function')
def sample_notification_model_with_organization(
        notify_db,
        notify_db_session,
        service=None,
        template=None,
        job=None,
        job_row_number=None,
        to_field=None,
        status='created',
        reference=None,
        sent_at=None,
        billable_units=1,
        personalisation=None,
        api_key=None,
        key_type=KEY_TYPE_NORMAL,
        sent_by=None,
        client_reference=None,
        rate_multiplier=1.0,
        normalised_to=None,
        postage=None,
        sms_sender_id=None
) -> Notification:
    created_at = datetime.utcnow()

    if service is None:
        service = create_service_model()

    if template is None:
        template = create_template_model(service=service)

    notification_id = uuid4()

    data = {
        'id': notification_id,
        'to': to_field if to_field else '+16502532222',
        'job_id': job.id if job else None,
        'job': job,
        'service_id': service.id,
        'service': service,
        'template': template,
        'template_id': template.id,
        'template_version': template.version,
        'status': status,
        'reference': reference,
        'created_at': created_at,
        'sent_at': sent_at,
        'billable_units': billable_units,
        'personalisation': personalisation,
        'notification_type': template.template_type,
        'api_key': api_key,
        'api_key_id': api_key and api_key.id,
        'key_type': api_key.key_type if api_key else key_type,
        'sent_by': sent_by,
        'updated_at': None,
        'client_reference': client_reference,
        'rate_multiplier': rate_multiplier,
        'normalised_to': normalised_to,
        'postage': postage,
        'sms_sender_id': sms_sender_id,
    }
    if job_row_number is not None:
        data['job_row_number'] = job_row_number
    notification = Notification(**data)

    return notification


@pytest.fixture
def sample_service(
    notify_db_session, sample_user, sample_permissions, sample_service_permissions, sample_sms_sender_v2
):
    created_service_ids: list = []

    def _sample_service(*args, **kwargs):

        # Handle where they are checking if it exists by name
        if kwargs.pop('check_if_service_exists', False) and 'service_name' in kwargs:
            service = notify_db_session.session.scalar(select(Service).where(Service.name == kwargs['service_name']))
            if service is not None:
                return service

        # We do not want create_service to create users because it does not clean them up
        if len(args) == 0 and 'user' not in kwargs:
            kwargs['user'] = sample_user(email=f'sample_service_{uuid4()}@va.gov')

        # Remove things that Service does not expect
        service_permissions = kwargs.pop('service_permissions', [EMAIL_TYPE, SMS_TYPE])
        user = kwargs.pop('user')

        service: Service = sample_service_helper(user, *args, **kwargs)
        service.users.append(user)

        sample_service_permissions(service, service_permissions)
        sample_permissions(user, service)
        sample_sms_sender_v2(service.id)
        # Service should be version 1 in the history after calling this
        version_service(service)

        created_service_ids.append(service.id)
        return service

    yield _sample_service
    service_cleanup(created_service_ids, notify_db_session.session)


def sample_service_helper(
        user,
        service_name=None,
        service_id=None,
        restricted=False,
        count_as_live=True,
        research_mode=False,
        active=True,
        email_from='',
        prefix_sms=False,
        message_limit=1000,
        organisation_type='other',
        go_live_user=None,
        go_live_at=None,
        crown=True,
        organisation=None,
        smtp_user=None
):
    service_name = service_name or f'sample service {uuid4()}'
    kwargs = locals()
    kwargs['created_by'] = kwargs.pop('user')
    kwargs['email_from'] = email_from or service_name.lower().replace(' ', '.')
    kwargs['id'] = kwargs.pop('service_id') or str(uuid4())
    kwargs['name'] = kwargs.pop('service_name')

    return Service(**kwargs)


def service_cleanup(service_ids: list, session: scoped_session) -> None:
    """
    Cleans up a list of services by deleting all dependencies then clearing the services. Services are used for almost
    everything we do, so the list below is extensive. Without all these here we will need specific ordering on the
    fixtures so one fixture cleans up before it makes it to the sample_service teardown.
    Moved this out of the sample_service fixture for clarity.
    """

    # This is an unfortunate reality of the deep dependency web of our database
    for service_id in service_ids:
        service = session.get(Service, service_id)
        if service is None:
            continue

        # Clear annual_billing
        session.execute(delete(AnnualBilling).where(AnnualBilling.service_id == service_id))

        # Clear ft_billing
        session.execute(delete(FactBilling).where(FactBilling.service_id == service_id))

        # Clear providers
        service.email_provider_id = None
        service.sms_provider_id = None

        # Clear service_letter_contacts
        for letter_contact in session.scalars(
            select(ServiceLetterContact).where(ServiceLetterContact.service_id == service_id)
        ).all():
            session.delete(letter_contact)

        # Clear template_folder
        for template_folder in session.scalars(
            select(TemplateFolder).where(TemplateFolder.service_id == service_id)
        ).all():
            session.delete(template_folder)

        # Clear user_to_service
        session.execute(delete(user_folder_permissions).where(user_folder_permissions.c.service_id == service_id))

        # Clear all keys
        for api_key in session.scalars(select(ApiKey).where(ApiKey.service_id == service_id)).all():
            session.delete(api_key)

        # Clear all permissions
        # session.execute(delete(ServicePermission).where(ServicePermission.service_id == service_id))
        for service_perm in session.scalars(
            select(ServicePermission).where(ServicePermission.service_id == service_id)
        ).all():
            if not inspect(service_perm).deleted:
                session.delete(service_perm)

        # Clear all permissions
        for perm in session.scalars(select(Permission).where(Permission.service_id == service_id)).all():
            if not inspect(perm).deleted:
                session.delete(perm)

        # Clear all service_sms_senders
        for sender in session.scalars(select(ServiceSmsSender).where(ServiceSmsSender.service_id == service_id)).all():
            session.delete(sender)

        # Clean up service servies_history
        # We do not have a all history models. This allows us to have a table for deletions
        # Can't be declared until the app context is declared
        ServicesHistory = Table('services_history', Service.get_history_model().metadata, autoload_with=db.engine)
        ServiceCallbackHistory = Table(
            'service_callback_history',
            ServiceCallback.get_history_model().metadata,
            autoload_with=db.engine
        )

        session.execute(delete(ServicesHistory).where(ServicesHistory.c.id == service_id))
        session.execute(delete(ServiceCallbackHistory).where(ServiceCallbackHistory.c.service_id == service_id))

        for service_callback in session.scalars(
            select(ServiceCallback).where(ServiceCallback.service_id == service_id)
        ).all():
            session.delete(service_callback)

        # Clear user_to_service
        for user_to_service in session.scalars(select(ServiceUser).where(ServiceUser.service_id == service_id)).all():
            session.delete(user_to_service)

        # Clear inbound_numbers
        session.execute(delete(InboundNumber).where(InboundNumber.service_id == service_id))

        # Clear service_email_reply_to
        session.execute(delete(ServiceEmailReplyTo).where(ServiceEmailReplyTo.service_id == service_id))

        session.execute(delete(Service).where(Service.id == service_id))
    session.commit()


@pytest.fixture
def sample_service_permissions(notify_db_session):
    service_permissions = []

    def _wrapper(service: Service, permissions: list = DEFAULT_SERVICE_PERMISSIONS):
        for perm in permissions:
            service_permission = ServicePermission(service_id=service.id, permission=perm)
            notify_db_session.session.add(service_permission)
            service.permissions.append(service_permission)
            service_permissions.append((service.id, perm))

        if len(permissions) > 0:
            notify_db_session.session.commit()
        return service.permissions

    yield _wrapper

    # Teardown
    # Set service.permissions.clear() ??
    for service_id, perm in service_permissions:
        stmt = select(ServicePermission).where(ServicePermission.service_id == service_id)\
                                        .where(ServicePermission.permission == perm)
        perm = notify_db_session.session.scalar(stmt)
        if perm is not None:
            notify_db_session.session.delete(perm)
    notify_db_session.session.commit()


@pytest.fixture
def sample_permissions(notify_db_session):
    perm_ids = []

    def _wrapper(user, service, permissions=default_service_permissions):
        for name in permissions:
            permission = Permission(permission=name, user=user, service=service)
            perm_ids.append(permission.id)
            notify_db_session.session.add(permission)
        notify_db_session.session.commit()

    yield _wrapper

    # Teardown
    for perm_id in perm_ids:
        permission = notify_db_session.session.scalar(select(Permission).where(Permission.id == perm_id))
        if permission is not None:
            notify_db_session.session.delete(permission)
    notify_db_session.session.commit()


@pytest.fixture(scope='function', name='sample_service_full_permissions')
def _sample_service_full_permissions(notify_db_session):
    service = create_service(
        service_name=f'sample service full permissions {uuid4()}',
        service_permissions=set(SERVICE_PERMISSION_TYPES),
        check_if_service_exists=True
    )

    # The inbound number is a unique, non-nullable 12-digit string.  With tests running
    # in parallel, this could result in a collision, although that's unlikely.
    number = str(randint(100000000000, 999999999999))
    create_inbound_number(number, service_id=service.id)
    yield service

    # Teardown
    dao_archive_service(service.id)


@pytest.fixture(scope='function', name='sample_service_custom_letter_contact_block')
def _sample_service_custom_letter_contact_block(sample_service):
    create_letter_contact(sample_service, contact_block='((contact block))')
    return sample_service


@pytest.fixture(scope="function")
def sample_service_data(sample_service):
    return ServiceData(sample_service)


def sample_template_helper(
    name,
    template_type,
    service,
    user,
    content="This is a template.",
    archived=False,
    folder=None,
    hidden=False,
    postage=None,
    subject_line="Subject",
    reply_to=None,
    reply_to_email=None,
    process_type=NORMAL,
    version=0,
    id=None,
) -> dict:
    """
    Return a dictionary of data for creating a Template or TemplateHistory instance.
    """

    data = {
        "name": name,
        "template_type": template_type,
        "content": content,
        "service": service,
        "created_by": user,
        "archived": archived,
        "folder": folder,
        "hidden": hidden,
        'postage': postage,
        "reply_to": reply_to,
        "reply_to_email": reply_to_email,
        "process_type": process_type,
        "version": version,
        "id": id,
    }

    if template_type == EMAIL_TYPE:
        data["subject"] = subject_line

    return data


@pytest.fixture
def sample_template(notify_db_session, sample_service, sample_user):
    template_ids = []

    def _wrapper(*args, **kwargs):
        assert len(args) == 0, "sample_template method does not accept positional arguments"
        # Mandatory arguments - ignore args
        kwargs['name'] = kwargs.get('name', f"function template {uuid4()}")
        kwargs['template_type'] = kwargs.get('template_type', SMS_TYPE)

        # Using fixtures as defaults creates those objects! Do not make a fixture the default param
        kwargs['user'] = kwargs.get('user') or sample_user()
        kwargs['service'] = kwargs.get('service') or sample_service()

        if 'subject' in kwargs:
            kwargs['subject_line'] = kwargs.pop('subject')

        template_data = sample_template_helper(*args, **kwargs)

        if kwargs['template_type'] == LETTER_TYPE:
            template_data["postage"] = kwargs.get("postage", "second")

        # Create template object and put it in the DB
        template = Template(**template_data)
        dao_create_template(template)
        template_ids.append(template.id)

        return template

    yield _wrapper

    # Teardown
    for template_id in template_ids:
        template = notify_db_session.session.get(Template, template_id)
        if template is None:  # It has already been cleaned up
            continue

        for history in notify_db_session.session.scalars(
            select(TemplateHistory).where(TemplateHistory.service_id == template.service_id)
        ).all():
            notify_db_session.session.delete(history)
        template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
        notify_db_session.session.delete(template_redacted)
        notify_db_session.session.delete(template)
    notify_db_session.session.commit()


@pytest.fixture(scope="function")
def sample_sms_template_func(notify_db_session, sample_service, sample_user):
    """
    Use this function-scoped SMS template for tests that don't need to modify the template.
    """

    template_data = sample_template_helper(
        f"function sms template {uuid4()}",
        SMS_TYPE, sample_service(), sample_user()
    )
    template = Template(**template_data)
    dao_create_template(template)

    yield template

    # Teardown
    template_history = notify_db_session.session.get(TemplateHistory, (template.id, template.version))
    notify_db_session.session.delete(template_history)
    template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    notify_db_session.session.delete(template_redacted)
    notify_db_session.session.delete(template)
    notify_db_session.session.commit()


@pytest.fixture(scope="session")
def sample_sms_template(notify_db, sample_service, sample_user, worker_id):
    """
    Use this session-scoped SMS template for tests that don't need to modify the template.
    """

    template_data = sample_template_helper(f"session sms template {worker_id}", SMS_TYPE, sample_service, sample_user)
    template = Template(**template_data)
    notify_db.session.add(template)
    notify_db.session.commit()

    yield template

    notify_db.session.delete(template)
    notify_db.session.commit()


@pytest.fixture(scope="session")
def sample_sms_template_history(notify_db, sample_service, sample_user, worker_id):
    """
    Use this session-scoped SMS TemplateHistory for tests that don't need to modify templates.
    Create a template history instance for any template instance used to create a Notification instance.
    Otherwise, attempting to create a Notification will lead to an InegrityError.

    Note that Notification instances have foreign keys to TemplateHistory instances rather than
    Template instances.
    """

    template_data = sample_template_helper(
        f"session sms template history {worker_id}", SMS_TYPE, sample_service, sample_user
    )
    template_history = TemplateHistory(**template_data)
    notify_db.session.add(template_history)
    notify_db.session.commit()

    yield template_history

    notify_db.session.delete(template_history)
    notify_db.session.commit()


@pytest.fixture(scope="function")
def sample_email_template_func(notify_db_session, sample_service, sample_user):
    """
    Use this function-scoped e-mail template for tests that don't need to modify the template.
    """

    template_data = sample_template_helper(
        f"function e-mail template {uuid4()}", EMAIL_TYPE, sample_service(), sample_user()
    )
    template = Template(**template_data)
    dao_create_template(template)

    yield template

    # Teardown
    template_history = notify_db_session.session.get(TemplateHistory, (template.id, template.version))
    notify_db_session.session.delete(template_history)
    template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    notify_db_session.session.delete(template_redacted)
    notify_db_session.session.delete(template)
    notify_db_session.session.commit()


@pytest.fixture(scope="function")
def sample_email_template_history(notify_db, sample_service, sample_user, worker_id):
    """
    Use this session-scoped e-mail TemplateHistory for tests that don't need to modify templates.
    Create a template history instance for any template instance used to create a Notification instance.
    Otherwise, attempting to create a Notification will lead to an InegrityError.

    Note that Notification instances have foreign keys to TemplateHistory instances rather than
    Template instances.
    """
    templates = []
    template_data = sample_template_helper(
        f"session e-mail template history {worker_id}", EMAIL_TYPE, sample_service(), sample_user()
    )
    template_history = TemplateHistory(**template_data)
    notify_db.session.add(template_history)
    notify_db.session.commit()
    templates.append(template_history)

    yield template_history

    for template in templates:
        notify_db.session.delete(template)
        notify_db.session.commit()


@pytest.fixture
def sample_template_without_sms_permission(notify_db_session, sample_template):
    service = create_service(service_permissions=[EMAIL_TYPE], check_if_service_exists=True)
    template = sample_template(service, template_type=SMS_TYPE)
    yield template

    # Teardown
    template_history = notify_db_session.session.get(TemplateHistory, (template.id, template.version))
    notify_db_session.session.delete(template_history)
    template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    notify_db_session.session.delete(template_redacted)
    notify_db_session.session.delete(template)
    notify_db_session.session.commit()


@pytest.fixture
def sample_template_with_placeholders(sample_template):
    new_template = sample_template(content="Hello (( Name))\nYour thing is due soon")
    assert new_template.template_type == SMS_TYPE, "This is the default."
    return new_template


@pytest.fixture
def sample_sms_template_with_html(sample_service, sample_template):
    # deliberate space and title case in placeholder
    sample_service.prefix_sms = True
    return sample_template(sample_service, content="Hello (( Name))\nHere is <em>some HTML</em> & entities")


@pytest.fixture
def sample_template_without_email_permission(notify_db_session, sample_template):
    service = create_service(service_permissions=[SMS_TYPE], check_if_service_exists=True)
    template = sample_template(service, template_type=EMAIL_TYPE)
    yield template

    # Teardown
    template_history = notify_db_session.session.get(TemplateHistory, (template.id, template.version))
    notify_db_session.session.delete(template_history)
    template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
    notify_db_session.session.delete(template_redacted)
    notify_db_session.session.delete(template)
    notify_db_session.session.commit()


@pytest.fixture
def sample_letter_template(sample_service_full_permissions, sample_template):
    return sample_template(sample_service_full_permissions, template_type=LETTER_TYPE, postage="second")


@pytest.fixture
def sample_trial_letter_template(sample_service_full_permissions, sample_template):
    sample_service_full_permissions.restricted = True
    return sample_template(sample_service_full_permissions, template_type=LETTER_TYPE)


@pytest.fixture
def sample_email_template_with_placeholders(sample_template):
    return sample_template(
        template_type=EMAIL_TYPE,
        subject="((name))",
        content="Hello ((name))\nThis is an email from GOV.UK",
    )


@pytest.fixture
def sample_email_template_with_reply_to(sample_template):
    return sample_template(
        template_type=EMAIL_TYPE,
        subject="((name))",
        content="Hello ((name))\nThis is an email from GOV.UK",
        reply_to_email="testing@email.com"
    )


@pytest.fixture
def sample_email_template_with_html(sample_template):
    return sample_template(
        template_type=EMAIL_TYPE,
        subject="((name)) <em>some HTML</em>",
        content="Hello ((name))\nThis is an email from GOV.UK with <em>some HTML</em>",
    )


@pytest.fixture
def sample_email_template_with_onsite_true(sample_template):
    return sample_template(
        template_type=EMAIL_TYPE,
        subject="((name))",
        content="Hello ((name))\nThis is an email from GOV.UK",
        onsite_notification=True,
    )


@pytest.fixture
def sample_api_key(notify_db_session, sample_service, worker_id):
    created_key_ids = {worker_id: []}

    def _sample_api_key(service=None, key_type=KEY_TYPE_NORMAL, key_name=None, expired=False):
        if service is None:
            service = sample_service()

        api_key = create_api_key(service, key_type, key_name, expired)
        version_api_key(api_key)

        if worker_id in created_key_ids:
            created_key_ids[worker_id].append(api_key.id)
        else:
            created_key_ids[worker_id] = [api_key.id]
        return api_key

    yield _sample_api_key

    for key_id in created_key_ids[worker_id]:
        key = notify_db_session.session.get(ApiKey, key_id)
        if key is None:
            continue

        # No model for api_keys_history
        ApiKeyHistory = Table('api_keys_history', ApiKey.get_history_model().metadata, autoload_with=db.engine)
        notify_db_session.session.execute(delete(ApiKeyHistory).where(ApiKeyHistory.c.id == key.id))
        notify_db_session.session.delete(key)
    notify_db_session.session.commit()


@pytest.fixture
def sample_user_service_api_key(notify_db_session, sample_user, sample_service, sample_api_key):
    """
    Return a related user, service, and API key.  The user and API key are associated with the service.
    The user is not admin, and the API key is "normal" type.
    """
    user = sample_user()
    service = sample_service(user=user)
    assert service.created_by == user
    api_key = sample_api_key(service)
    assert api_key in service.api_keys
    return user, service, api_key


@pytest.fixture(scope='function')
def sample_test_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(
        service,
        key_type=KEY_TYPE_TEST
    )


@pytest.fixture(scope='function')
def sample_team_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(
        service,
        key_type=KEY_TYPE_TEAM
    )


@pytest.fixture
def sample_job(notify_db_session):
    created_jobs = []

    def _sample_job(template, **kwargs):
        job = create_job(template, **kwargs)
        created_jobs.append(job)
        return job

    yield _sample_job

    for job in created_jobs:
        notify_db_session.session.delete(job)
    notify_db_session.session.commit()


@pytest.fixture
def email_job_with_placeholders(sample_job, sample_email_template_with_placeholders):
    return sample_job(sample_email_template_with_placeholders)


@pytest.fixture
def sample_job_with_placeholdered_template(sample_job, sample_template_with_placeholders):
    return sample_job(sample_template_with_placeholders)


@pytest.fixture
def sample_scheduled_job(sample_template_with_placeholders):
    return create_job(
        sample_template_with_placeholders,
        job_status='scheduled',
        scheduled_for=(datetime.utcnow() + timedelta(minutes=60)).isoformat()
    )


@pytest.fixture
def sample_email_job(notify_db,
                     notify_db_session,
                     service=None,
                     template=None):
    if service is None:
        service = create_service(check_if_service_exists=True)
    if template is None:
        template = sample_email_template_func(
            notify_db,
            notify_db_session,
            service=service)
    job_id = uuid4()
    data = {
        'id': job_id,
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_by': service.created_by
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture
def sample_letter_job(sample_letter_template):
    service = sample_letter_template.service
    data = {
        'id': uuid4(),
        'service_id': service.id,
        'service': service,
        'template_id': sample_letter_template.id,
        'template_version': sample_letter_template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_at': datetime.utcnow(),
        'created_by': service.created_by,
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture(scope='function')
def sample_notification_with_job(
        notify_db,
        notify_db_session,
        sample_sms_sender,
        service=None,
        template=None,
        job=None,
        job_row_number=None,
        to_field=None,
        status='created',
        reference=None,
        created_at=None,
        sent_at=None,
        billable_units=1,
        personalisation=None,
        api_key=None,
        key_type=KEY_TYPE_NORMAL
):
    if service is None:
        service = create_service(check_if_service_exists=True)
    if template is None:
        template = create_template(service=service)
        assert template.template_type == SMS_TYPE, "This is the default template type."
    if job is None:
        job = create_job(template=template)

    yield create_notification(
        template=template,
        job=job,
        job_row_number=job_row_number if job_row_number is not None else None,
        to_field=to_field,
        status=status,
        reference=reference,
        created_at=created_at,
        sent_at=sent_at,
        billable_units=billable_units,
        personalisation=personalisation,
        api_key=api_key,
        key_type=key_type,
        sms_sender_id=sample_sms_sender.id
    )

    # Teardown
    notify_db_session.session.execute(delete(Notification).where(Notification.service_id == service.id))


@pytest.fixture
def sample_notification(notify_db_session, sample_api_key, sample_service, sample_template):  # noqa C901
    # TODO: Refactor to use fixtures for teardown purposes
    created_notifications = []
    created_scheduled_notifications = []
    created_service_ids = []
    created_templates = []
    created_api_keys = []

    def _sample_notification(*args, **kwargs):
        if kwargs.get("created_at") is None:
            kwargs["created_at"] = datetime.utcnow()

        if kwargs.get("template") is None:
            service = sample_service(check_if_service_exists=True)
            created_service_ids.append(service.id)

            template = sample_template(service=service)
            kwargs["template"] = template
            created_templates.append(template)
            assert template.template_type == SMS_TYPE, "This is the default template type."

        if kwargs.get("job") is None and kwargs.get("api_key") is None:
            api_key = ApiKey.query.filter(
                ApiKey.service == kwargs["template"].service,
                ApiKey.key_type == kwargs.get("key_type", KEY_TYPE_NORMAL)
            ).first()

            if not api_key:
                api_key = sample_api_key(kwargs["template"].service, key_type=kwargs.get("key_type", KEY_TYPE_NORMAL))
                kwargs["api_key"] = api_key
                created_api_keys.append(api_key)

        notification = create_notification(*args, **kwargs)
        created_notifications.append(notification)

        if kwargs.get("scheduled_for"):
            scheduled_notification = ScheduledNotification(
                id=uuid4(),
                notification_id=notification.id,
                scheduled_for=datetime.strptime(kwargs["scheduled_for"], "%Y-%m-%d %H:%M")
            )

            if kwargs.get("status") != "created":
                scheduled_notification.pending = False

            notify_db_session.session.add(scheduled_notification)
            notify_db_session.session.commit()
            created_scheduled_notifications.append(scheduled_notification)

        return notification

    yield _sample_notification

    # Teardown.  Order matters.  Delete API keys last.
    for scheduled_notification in created_scheduled_notifications:
        notify_db_session.session.delete(scheduled_notification)
    for notification in created_notifications:
        # Other things may delete a notification first.  Check before deleting.
        if not inspect(notification).detached:
            notify_db_session.session.delete(notification)
    for template in created_templates:
        for hist in notify_db_session.session.scalars(select(TemplateHistory)
                                                      .where(TemplateHistory.id == template.id)).all():
            notify_db_session.session.delete(hist)
        template_redacted = notify_db_session.session.get(TemplateRedacted, template.id)
        notify_db_session.session.delete(template_redacted)
        notify_db_session.session.delete(template)
    service_cleanup(created_service_ids, notify_db_session.session)
    for api_key in created_api_keys:
        # Other things may delete an API key first.  Check before deleting.
        if not inspect(api_key).detached:
            notify_db_session.session.delete(api_key)
    notify_db_session.session.commit()


@pytest.fixture
def sample_letter_notification(notify_db_session, sample_notification, sample_service, sample_template):
    address = {
        'address_line_1': 'A1',
        'address_line_2': 'A2',
        'address_line_3': 'A3',
        'address_line_4': 'A4',
        'address_line_5': 'A5',
        'address_line_6': 'A6',
        'postcode': 'A_POST',
    }
    service = sample_service(service_permissions=SERVICE_PERMISSION_TYPES)
    template = sample_template(service=service, template_type=LETTER_TYPE, postage='postage')
    notification = sample_notification(template=template, reference='foo', personalisation=address)

    yield notification

    # Teardown only if the object wasn't deleted already.
    if not inspect(notification).detached:
        notify_db_session.session.delete(notification)
        notify_db_session.session.commit()


@pytest.fixture
def sample_email_notification(notify_db_session):
    created_at = datetime.utcnow()
    service = create_service(check_if_service_exists=True)
    template = create_template(service, template_type=EMAIL_TYPE)
    job = create_job(template)

    notification_id = uuid4()

    to = 'foo@bar.com'

    data = {
        'id': notification_id,
        'to': to,
        'job_id': job.id,
        'job': job,
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'status': 'created',
        'reference': None,
        'created_at': created_at,
        'billable_units': 0,
        'personalisation': None,
        'notification_type': template.template_type,
        'api_key_id': None,
        'key_type': KEY_TYPE_NORMAL,
        'job_row_number': 1,
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    return notification


@pytest.fixture(scope='function')
def sample_notification_history(
        notify_db,
        notify_db_session,
        sample_sms_template_func,
        status='created',
        created_at=None,
        notification_type=None,
        key_type=KEY_TYPE_NORMAL,
        sent_at=None,
        api_key=None,
        sms_sender_id=None
):
    if created_at is None:
        created_at = datetime.utcnow()

    if sent_at is None:
        sent_at = datetime.utcnow()

    if notification_type is None:
        notification_type = sample_sms_template_func.template_type
        assert notification_type == SMS_TYPE, "This is the default."

    api_key_teardown = None
    if not api_key:
        api_key = create_api_key(sample_sms_template_func.service, key_type=key_type)
        api_key_teardown = api_key

    notification_history = NotificationHistory(
        id=uuid4(),
        service=sample_sms_template_func.service,
        template_id=sample_sms_template_func.id,
        template_version=sample_sms_template_func.version,
        status=status,
        created_at=created_at,
        notification_type=notification_type,
        key_type=key_type,
        api_key=api_key,
        api_key_id=api_key and api_key.id,
        sent_at=sent_at,
        sms_sender_id=sms_sender_id
    )
    notify_db.session.add(notification_history)
    notify_db.session.commit()

    yield notification_history

    # Teardown
    if api_key_teardown is not None:
        key_to_delete = notify_db.session.get(ApiKey, api_key.id)
        notify_db.session.delete(key_to_delete)
    notify_db.session.delete(notification_history)
    notify_db.session.commit()


@pytest.fixture(scope='function')
def mock_celery_send_sms_code(mocker):
    return mocker.patch('app.celery.tasks.send_sms_code.apply_async')


@pytest.fixture(scope='function')
def mock_celery_email_registration_verification(mocker):
    return mocker.patch('app.celery.tasks.email_registration_verification.apply_async')


@pytest.fixture(scope='function')
def mock_celery_send_email(mocker):
    return mocker.patch('app.celery.tasks.send_email.apply_async')


@pytest.fixture(scope='function')
def mock_encryption(mocker):
    return mocker.patch('app.encryption.encrypt', return_value="something_encrypted")


@pytest.fixture(scope="function")
def sample_invited_user(notify_db_session):
    service = create_service(check_if_service_exists=True)
    to_email_address = 'invited_user@digital.gov.uk'

    from_user = service.users[0]

    data = {
        'service': service,
        'email_address': to_email_address,
        'from_user': from_user,
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': ['folder_1_id', 'folder_2_id'],
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)

    yield invited_user

    notify_db_session.session.delete(invited_user)
    notify_db_session.session.commit()


@pytest.fixture(scope="function")
def sample_invited_org_user(notify_db_session, sample_organisation, sample_user):
    invited_organisation_user = create_invited_org_user(sample_organisation, sample_user)

    yield invited_organisation_user

    notify_db_session.session.delete(invited_organisation_user)
    notify_db_session.session.commit()


@pytest.fixture(scope='function')
def sample_user_service_permission(
        notify_db_session, service=None, user=None, permission="manage_settings"
):
    if user is None:
        user = create_user()
    if service is None:
        service = create_service(user=user, check_if_service_exists=True)
    data = {
        'user': user,
        'service': service,
        'permission': permission,
    }
    p_model = Permission.query.filter_by(
        user=user,
        service=service,
        permission=permission).first()
    if not p_model:
        p_model = Permission(**data)
        db.session.add(p_model)
        db.session.commit()
    return p_model


@pytest.fixture(scope='function')
def fake_uuid():
    return "6ce466d0-fd6a-11e5-82f5-e0accb9d11a6"


@pytest.fixture(scope='function')
def current_sms_provider():
    return ProviderDetails.query.filter_by(
        notification_type='sms'
    ).order_by(
        asc(ProviderDetails.priority)
    ).first()


@pytest.fixture
def sample_provider(notify_db_session):
    provider_ids = []

    def _wrapper(
        identifier: str = PINPOINT_PROVIDER,
        get: bool = False,
        display_name: str = '',
        priority: int = 10,
        notification_type: Union[EMAIL_TYPE, SMS_TYPE] = SMS_TYPE,
        active: bool = True,
        supports_international: bool = False,
        created_by: User = None,
        created_by_id: UUID = None,
    ):
        assert identifier in PROVIDERS
        if get:
            stmt = select(ProviderDetails).where(ProviderDetails.identifier == identifier)
            provider = notify_db_session.session.scalar(stmt)
        else:
            data = {
                'display_name': display_name or f'provider_{uuid4()}',
                'identifier': identifier,
                'priority': priority,
                'notification_type': notification_type,
                'active': active,
                'supports_international': supports_international,
                'created_by': created_by,
                'created_by_id': created_by_id,
            }

            # Set created_by or created_by_id if the other exists
            if created_by and not created_by_id:
                data['created_by_id'] = str(created_by.id)
            if created_by_id and not created_by:
                data['created_by'] = notify_db_session.session.get(User, created_by_id)

            provider = ProviderDetails(**data)
            notify_db_session.session.add(provider)
            notify_db_session.session.commit()
            provider_ids.append(provider.id)

        return provider

    yield _wrapper

    # Teardown
    for provider_id in provider_ids:
        provider = notify_db_session.session.get(ProviderDetails, provider_id)
        if provider is None:
            continue

        notify_db_session.session.execute(delete(ProviderDetailsHistory)
                                          .where(ProviderDetailsHistory.id == provider_id))
        notify_db_session.session.delete(provider)
    notify_db_session.session.commit()


@pytest.fixture(scope='function')
def ses_provider():
    return ProviderDetails.query.filter_by(identifier='ses').one()


@pytest.fixture(scope='function')
def firetext_provider():
    return ProviderDetails.query.filter_by(identifier='firetext').one()


@pytest.fixture(scope='function')
def mmg_provider():
    return ProviderDetails.query.filter_by(identifier='mmg').one()


@pytest.fixture(scope='function')
def mock_firetext_client(mocker, statsd_client=None):
    client = FiretextClient()
    statsd_client = statsd_client or mocker.Mock()
    current_app = mocker.Mock(config={
        'FIRETEXT_URL': 'https://example.com/firetext',
        'FIRETEXT_API_KEY': 'foo',
        'FROM_NUMBER': 'bar'
    })
    client.init_app(current_app, statsd_client)
    return client


@pytest.fixture(scope='function')
def email_verification_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID',
        content='((user_name)) use ((url)) to complete registration',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def invitation_email_template(notify_db,
                              notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = '((user_name)) is invited to Notify by ((service_name)) ((url)) to complete registration',
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='INVITATION_EMAIL_TEMPLATE_ID',
        content=content,
        subject='Invitation to ((service_name))',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def org_invite_email_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID',
        content='((user_name)) ((organisation_name)) ((url))',
        subject='Invitation to ((organisation_name))',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def password_reset_email_template(notify_db,
                                  notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='PASSWORD_RESET_TEMPLATE_ID',
        content='((user_name)) you can reset password by clicking ((url))',
        subject='Reset your password',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def verify_reply_to_address_email_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID',
        content="Hi,This address has been provided as the reply-to email address so we are verifying if it's working",
        subject='Your GOV.UK Notify reply-to email address',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def team_member_email_edit_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID',
        content='Hi ((name)) ((servicemanagername)) changed your email to ((email address))',
        subject='Your GOV.UK Notify email address has changed',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def team_member_mobile_edit_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID',
        content='Your mobile number was changed by ((servicemanagername)).',
        template_type='sms'
    )


@pytest.fixture(scope='function')
def already_registered_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    content = """Sign in here: ((signin_url)) If you’ve forgotten your password,
                          you can reset it here: ((forgot_password_url)) feedback:((feedback_url))"""
    return create_custom_template(
        service=service, user=user,
        template_config_name='ALREADY_REGISTERED_EMAIL_TEMPLATE_ID',
        content=content,
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def contact_us_template(notify_db,
                        notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    content = """User ((user)) sent the following message:
        ((message))"""
    return create_custom_template(
        service=service, user=user,
        template_config_name='CONTACT_US_TEMPLATE_ID',
        content=content,
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def change_email_confirmation_template(notify_db,
                                       notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = """Hi ((name)),
              Click this link to confirm your new email address:
              ((url))
              If you didn’t try to change the email address for your GOV.UK Notify account, let us know here:
              ((feedback_url))"""
    template = create_custom_template(
        service=service,
        user=user,
        template_config_name='CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID',
        content=content,
        template_type=EMAIL_TYPE
    )
    return template


@pytest.fixture(scope='function')
def smtp_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='SMTP_TEMPLATE_ID',
        content=('((message))'),
        subject='((subject))',
        template_type=EMAIL_TYPE
    )


@pytest.fixture(scope='function')
def mou_signed_templates(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    import importlib
    alembic_script = importlib.import_module('migrations.versions.0298_add_mou_signed_receipt')

    return {
        config_name: create_custom_template(
            service,
            user,
            config_name,
            EMAIL_TYPE,
            content='\n'.join(
                next(
                    x
                    for x in alembic_script.templates
                    if x['id'] == current_app.config[config_name]
                )['content_lines']
            ),
        )
        for config_name in [
            'MOU_SIGNER_RECEIPT_TEMPLATE_ID',
            'MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID',
            'MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID',
            'MOU_NOTIFY_TEAM_ALERT_TEMPLATE_ID',
        ]
    }


def create_custom_template(service, user, template_config_name, template_type, content='', subject=None):
    template = Template.query.get(current_app.config[template_config_name])
    if not template:
        data = {
            'id': current_app.config[template_config_name],
            'name': template_config_name,
            'template_type': template_type,
            'content': content,
            'service': service,
            'created_by': user,
            'subject': subject,
            'archived': False
        }
        template = Template(**data)
        db.session.add(template)
        db.session.add(create_history(template, TemplateHistory))
        db.session.commit()
    return template


def notify_service(notify_db_session):
    user = create_user()
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])
    if not service:
        service = Service(
            name='Notify Service',
            message_limit=1000,
            restricted=False,
            email_from='notify.service',
            created_by=user,
            prefix_sms=False,
        )
        dao_create_service(
            service=service,
            service_id=current_app.config['NOTIFY_SERVICE_ID'],
            user=user
        )

        data = {
            'service': service,
            'email_address': "notify@gov.uk",
            'is_default': True,
        }
        reply_to = ServiceEmailReplyTo(**data)

        db.session.add(reply_to)
        db.session.commit()

    return service, user


@pytest.fixture(scope='function')
def sample_service_whitelist(notify_db_session):
    service = create_service(check_if_service_exists=True)
    whitelisted_user = service_whitelist.a_service_whitelist(service_id=service.id)
    notify_db_session.session.add(whitelisted_user)
    notify_db_session.session.commit()
    return whitelisted_user


@pytest.fixture(scope='function')
def sample_provider_rate(notify_db_session, valid_from=None, rate=None, provider_identifier=None):
    create_provider_rates(
        provider_identifier=provider_identifier if provider_identifier is not None else 'mmg',
        valid_from=valid_from if valid_from is not None else datetime.utcnow(),
        rate=rate if rate is not None else 1,
    )


@pytest.fixture
def sample_inbound_sms(notify_db_session, sample_service, sample_inbound_number):
    inbound_sms_list = []

    def _wrapper(
            service=None,
            notify_number=None,
            user_number='+16502532222',
            provider_date=None,
            provider_reference='foo',
            content='Hello',
            provider="mmg",
            created_at=None
    ):
        # Set values if they came in None
        service = service or sample_service()
        provider_date = provider_date or datetime.utcnow()
        created_at = created_at or datetime.utcnow()
        # if notify_number comes in None it is handled by creating an inbound number for the service

        if not service.inbound_numbers:
            # Create inbound_number attached to the service
            sample_inbound_number(number=notify_number,
                                  provider=provider,
                                  service_id=service.id)

        inbound_sms = InboundSms(service=service,
                                 created_at=created_at,
                                 notify_number=notify_number or service.inbound_numbers[0].number,
                                 user_number=user_number,
                                 provider_date=provider_date,
                                 provider_reference=provider_reference,
                                 content=content,
                                 provider=provider)

        notify_db_session.session.add(inbound_sms)
        notify_db_session.session.commit()
        inbound_sms_list.append(inbound_sms)

        return inbound_sms

    yield _wrapper

    # Teardown
    for inbound_sms in inbound_sms_list:
        notify_db_session.session.delete(inbound_sms)
    notify_db_session.session.commit()


@pytest.fixture
def sample_inbound_number(notify_db_session, sample_service):
    inbound_number_ids = []

    def _wrapper(
        number=None,
        provider='ses',
        active=True,
        service_id=None,
        url_endpoint=None,
        self_managed=False
    ):
        # Default to the correct amount of characters
        number = number or f'1{randint(100000000, 999999999)}'

        inbound_number = InboundNumber(
            id=uuid4(),
            number=number,
            provider=provider,
            active=active,
            service_id=service_id or sample_service(),
            url_endpoint=url_endpoint,
            self_managed=self_managed
        )

        notify_db_session.session.add(inbound_number)
        notify_db_session.session.commit()
        inbound_number_ids.append(inbound_number.id)

        return inbound_number

    yield _wrapper

    # Teardown
    for inbound_number_id in inbound_number_ids:
        inbound_number = notify_db_session.session.get(InboundNumber, inbound_number_id)
        if inbound_number is None:
            continue

        notify_db_session.session.delete(inbound_number)
    notify_db_session.session.commit()


@pytest.fixture
def sample_inbound_numbers(notify_db_session, sample_service):
    service = create_service(service_name='sample service 2', check_if_service_exists=True)
    inbound_numbers = list()
    inbound_numbers.append(create_inbound_number(number='1', provider='mmg'))
    inbound_numbers.append(create_inbound_number(number='2', provider='mmg', active=False, service_id=service.id))
    inbound_numbers.append(create_inbound_number(number='3', provider='firetext', service_id=sample_service.id))
    return inbound_numbers


@pytest.fixture(scope="function")
def sample_organisation(notify_db_session, worker_id):
    org = Organisation(name=f"sample organisation {worker_id}")
    dao_create_organisation(org)

    yield org

    notify_db_session.session.delete(org)
    notify_db_session.session.commit()


@pytest.fixture
def sample_fido2_key(notify_db_session):
    user = create_user()
    key = Fido2Key(name='sample key', key="abcd", user_id=user.id)
    save_fido2_key(key)
    return key


@pytest.fixture
def aws_credentials():
    os.environ['AWS_ACCESS_KEY_ID'] = "testing"
    os.environ['AWS_SECRET_ACCESS_KEY'] = "testing"
    os.environ['AWS_SESSION_TOKEN'] = "testing"
    os.environ['AWS_SECURITY_TOKEN'] = "testing"


@pytest.fixture
def sample_login_event(notify_db_session):
    user = create_user()
    event = LoginEvent(data={"ip": "8.8.8.8", "user-agent": "GoogleBot"}, user_id=user.id)
    save_login_event(event)
    return event


@pytest.fixture
def restore_provider_details(notify_db_session):
    """
    We view ProviderDetails as a static in notify_db_session, since we don't modify it... except we do, we updated
    priority. This fixture is designed to be used in tests that will knowingly touch provider details, to restore them
    to previous state.

    Note: This doesn't technically require notify_db_session (only notify_db), but kept as a requirement to encourage
    good usage.  If you're modifying ProviderDetails's state then it's good to clear down the rest of the DB too.
    """

    existing_provider_details = ProviderDetails.query.all()
    existing_provider_details_history = ProviderDetailsHistory.query.all()

    # make_transient removes the objects from the session (because we will delete them later).
    for epd in existing_provider_details:
        make_transient(epd)
    for epdh in existing_provider_details_history:
        make_transient(epdh)

    yield notify_db_session

    # also delete these as they depend on provider_details
    ProviderRates.query.delete()
    ProviderDetails.query.delete()
    ProviderDetailsHistory.query.delete()
    notify_db_session.session.commit()
    notify_db_session.session.add_all(existing_provider_details)
    notify_db_session.session.add_all(existing_provider_details_history)
    notify_db_session.session.commit()


@pytest.fixture
def admin_request(client):
    class AdminRequest:
        app = client.application

        @staticmethod
        def get(endpoint, _expected_status=200, **endpoint_kwargs):
            resp = client.get(
                url_for(endpoint, **(endpoint_kwargs or {})),
                headers=[create_admin_authorization_header()]
            )

            assert resp.status_code == _expected_status
            return resp.json

        @staticmethod
        def post(endpoint, _data=None, _expected_status=200, **endpoint_kwargs):
            resp = client.post(
                url_for(endpoint, **(endpoint_kwargs or {})),
                data=json.dumps(_data),
                headers=[('Content-Type', 'application/json'), create_admin_authorization_header()]
            )

            assert resp.status_code == _expected_status
            return resp.json if resp.get_data() else None

        @staticmethod
        def patch(endpoint, _data=None, _expected_status=200, **endpoint_kwargs):
            resp = client.patch(
                url_for(endpoint, **(endpoint_kwargs or {})),
                data=json.dumps(_data),
                headers=[('Content-Type', 'application/json'), create_admin_authorization_header()]
            )

            assert resp.status_code == _expected_status
            return resp.json if resp.get_data() else None

        @staticmethod
        def delete(endpoint, _expected_status=204, **endpoint_kwargs):
            resp = client.delete(
                url_for(endpoint, **(endpoint_kwargs or {})),
                headers=[create_admin_authorization_header()]
            )

            assert resp.status_code == _expected_status
            return resp.json if resp.get_data() else None

    return AdminRequest


@pytest.fixture(scope='function')
def mock_sms_client(mocker):
    mocked_client = SmsClient()
    mocker.patch.object(mocked_client, 'send_sms', return_value='some-reference')
    mocker.patch.object(mocked_client, 'get_name', return_value='Fake SMS Client')
    mocker.patch('app.delivery.send_to_providers.client_to_use', return_value=mocked_client)
    return mocked_client


@pytest.fixture(scope='function')
def mock_email_client(mocker):
    mocked_client = EmailClient()
    mocker.patch.object(mocked_client, 'send_email', return_value='message id')
    mocker.patch.object(mocked_client, 'get_name', return_value='Fake Email Client')
    mocker.patch('app.delivery.send_to_providers.client_to_use', return_value=mocked_client)
    return mocked_client


@pytest.fixture(scope='function')
def mocked_build_ga_pixel_url(mocker):
    mocked_builder = mocker.patch('app.googleanalytics.pixels.build_ga_pixel_url', return_value='url')
    return mocked_builder


@pytest.fixture(scope='function')
def mocked_provider_stats(sample_user, mocker):
    return [
        mocker.Mock(**{
            'id': uuid4(),
            'display_name': 'foo',
            'identifier': 'foo',
            'priority': 10,
            'notification_type': 'sms',
            'active': True,
            'updated_at': datetime.utcnow(),
            'supports_international': False,
            'created_by_name': sample_user().name,
            'load_balancing_weight': 25,
            'current_month_billable_sms': randrange(100)  # nosec
        }),
        mocker.Mock(**{
            'id': uuid4(),
            'display_name': 'bar',
            'identifier': 'bar',
            'priority': 20,
            'notification_type': 'sms',
            'active': True,
            'updated_at': datetime.utcnow(),
            'supports_international': False,
            'created_by_name': sample_user().name,
            'load_balancing_weight': 75,
            'current_month_billable_sms': randrange(100)  # nosec
        })
    ]


def datetime_in_past(days=0, seconds=0):
    return datetime.now(tz=pytz.utc) - timedelta(days=days, seconds=seconds)


@pytest.fixture
def sample_sms_sender_v2(notify_db_session, worker_id):
    sms_sender_ids = {worker_id: []}

    def _wrapper(
        service_id,
        sms_sender=current_app.config['FROM_NUMBER'],
        is_default=True,
        inbound_number_id=None,
        rate_limit=None,
        rate_limit_interval=None,
        sms_sender_specifics=None,
    ):
        data = {
            'service_id': service_id,
            'sms_sender': sms_sender,
            'is_default': is_default,
            'inbound_number_id': inbound_number_id,
            'rate_limit': rate_limit,
            'rate_limit_interval': rate_limit_interval,
            'sms_sender_specifics': sms_sender_specifics,
        }

        service_sms_sender = ServiceSmsSender(**data)
        notify_db_session.session.add(service_sms_sender)
        notify_db_session.session.commit()
        if worker_id in sms_sender_ids:
            sms_sender_ids[worker_id].append(service_sms_sender.id)
        else:
            sms_sender_ids[worker_id] = [service_sms_sender.id]

        return service_sms_sender

    yield _wrapper

    # Teardown
    # Fails if any notifications were sent
    for sms_sender_id in sms_sender_ids[worker_id]:
        sms_sender = notify_db_session.session.scalar(select(ServiceSmsSender)
                                                      .where(ServiceSmsSender.id == sms_sender_id))
        if sms_sender is not None:
            notify_db_session.session.delete(sms_sender)
    notify_db_session.session.commit()


@pytest.fixture(scope='function')
def sample_sms_sender(notify_db_session, sample_service):
    created_sms_senders = []

    def _sample_sms_sender(service_id: str):
        service_sms_sender = dao_add_sms_sender_for_service(service_id, "+12025555555", True)
        created_sms_senders.append(service_sms_sender)
        return service_sms_sender

    yield _sample_sms_sender

    # Teardown
    for sms_sender in created_sms_senders:
        notify_db_session.session.delete(sms_sender)
    notify_db_session.session.commit()


@pytest.fixture(scope="function")
def sample_communication_item(notify_db_session, worker_id):
    # Although unlikely, this can cause a duplicate Profile ID contraint failure.
    # If that happens, re-run the failing tests.
    va_profile_item_id = randint(500, 100000)
    communication_item = CommunicationItem(id=uuid4(), va_profile_item_id=va_profile_item_id, name=worker_id)
    notify_db_session.session.add(communication_item)
    notify_db_session.session.commit()
    assert communication_item.default_send_indicator, "Should be True by default."

    yield communication_item

    notify_db_session.session.delete(communication_item)
    notify_db_session.session.commit()


@pytest.fixture
def sample_service_with_inbound_number(
        notify_db_session,
        sample_service,
        inbound_number='1234567'
):
    teardown_tuples = []

    def _wrapper(*args, **kwargs):
        if kwargs.get('service') is None:
            # Sample service does not accept inbound_number, keep the name
            inbound_number = kwargs.pop('inbound_number')
            service = sample_service(*args, **kwargs)

        sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).first()
        inbound = create_inbound_number(number=inbound_number)
        dao_update_service_sms_sender(
            service_id=service.id,
            service_sms_sender_id=sms_sender.id,
            sms_sender=inbound_number,
            inbound_number_id=inbound.id
        )
        teardown_tuples.append((inbound, sms_sender))
        return service

    yield _wrapper

    # Teardown
    for inbound, sms_sender in teardown_tuples:
        # Cannot delete the sender if there's an inbound attached
        notify_db_session.session.delete(inbound)
        # Can't default default senders normally
        sms_sender.is_default = False
        notify_db_session.session.delete(sms_sender)
    notify_db_session.session.commit()
    # Service is cleaned elsewhere or in teardown of sample_service


@pytest.fixture
def sample_service_email_reply_to(notify_db_session, sample_service):
    service_email_reply_to_ids = []

    def _wrapper(service=None, **kwargs):
        data = {
            'service': service or sample_service(),
            'email_address': kwargs.get('email_address', 'vanotify@va.gov'),
            'is_default': True
        }
        service_email_reply_to = ServiceEmailReplyTo(**data)

        notify_db_session.session.add(service_email_reply_to)
        notify_db_session.session.commit()

        service_email_reply_to_ids.append(service_email_reply_to.id)
        return service_email_reply_to

    yield _wrapper

    # Teardown
    # Unsafe to teardown with objects, have to use ids to look up the object
    for sert_id in service_email_reply_to_ids:
        sert = notify_db_session.session.get(ServiceEmailReplyTo, sert_id)
        notify_db_session.session.delete(sert)
    notify_db_session.session.commit()


#######################################################################################################################
#                                                                                                                     #
#                                                 SESSION-SCOPED                                                      #
#                                                                                                                     #
#######################################################################################################################

# These exist because a few tests are expecting VA Notify-specific resources to exist. Attempting to utilize them with
# function-scoped fixtures leads to race conditions.

@pytest.fixture(scope='session')
def sample_notify_service_user_session(
    notify_db, sample_service_session, sample_service_email_reply_to_session, sample_user_session
):
    def _wrapper():
        u_id = current_app.config['NOTIFY_USER_ID']
        s_id = current_app.config['NOTIFY_SERVICE_ID']

        # We only want these created if they are not already made. This was session-scoped before
        user = notify_db.session.get(User, u_id) or sample_user_session(user_id=u_id)

        service = (
            notify_db.session.get(Service, s_id) or
            sample_service_session(
                service_name='Notify Service',
                email_from='notify.service',
                user=user,
                service_id=s_id
            )
        )

        sample_service_email_reply_to_session(service)
        return service, user

    return _wrapper
    # Teardown not required


@pytest.fixture(scope='session')
def sample_service_session(notify_db, sample_user_session):
    created_service_ids: list = []

    def _wrapper(*args, **kwargs):
        # We do not want create_service to create users because it does not clean them up
        if len(args) == 0 and 'user' not in kwargs:
            kwargs['user'] = sample_user_session()

        service: Service = create_service(*args, **kwargs)

        # The session is different (dao) so we can't just use save the
        # session object for deletion. Save the ID, and query it later.
        created_service_ids.append(service.id)
        return service

    yield _wrapper
    service_cleanup(created_service_ids, notify_db.session)


@pytest.fixture(scope='session')
def sample_service_email_reply_to_session(notify_db, sample_service_session):
    service_email_reply_to_ids = []

    def _wrapper(service=None, **kwargs):
        data = {
            'service': service or sample_service_session(),
            'email_address': 'vanotify@va.gov',
            'is_default': True
        }
        service_email_reply_to = ServiceEmailReplyTo(**data)

        notify_db.session.add(service_email_reply_to)
        notify_db.session.commit()

        service_email_reply_to_ids.append(service_email_reply_to.id)
        return service_email_reply_to

    yield _wrapper

    # Teardown
    # Unsafe to teardown with objects, have to use ids to look up the object
    for sert_id in service_email_reply_to_ids:
        sert = notify_db.session.get(ServiceEmailReplyTo, sert_id)
        notify_db.session.delete(sert)
    notify_db.session.commit()


@pytest.fixture(scope='session')
def sample_template_session(notify_db, sample_service_session, sample_user_session):
    """
    Use this session-scoped SMS template for tests that don't need to modify the template.
    """
    template_ids = []

    def _wrapper(*args, **kwargs):
        # Guard statements
        assert len(args) == 0, "sample_template method does not accept positional arguments"
        if str(kwargs.get('id')) in template_ids:
            return notify_db.session.get(Template, kwargs['id'])

        # Mandatory arguments - ignore args
        kwargs['name'] = kwargs.get('name', f"function template {uuid4()}")
        kwargs['template_type'] = kwargs.get('template_type', SMS_TYPE)

        # Using fixtures as defaults creates those objects! Do not make a fixture the default param
        kwargs['user'] = kwargs.get('user') or sample_user_session()
        kwargs['service'] = kwargs.get('service') or sample_service_session()

        if 'subject' in kwargs:
            kwargs['subject_line'] = kwargs.pop('subject')

        template_data = sample_template_helper(*args, **kwargs)

        if kwargs['template_type'] == LETTER_TYPE:
            template_data["postage"] = kwargs.get("postage", "second")

        # Create template object and put it in the DB
        template = Template(**template_data)
        dao_create_template(template)
        template_ids.append(str(template.id))

        return template

    yield _wrapper

    # Teardown
    for template_id in template_ids:
        template = notify_db.session.get(Template, template_id)
        for history in notify_db.session.scalars(
            select(TemplateHistory).where(TemplateHistory.service_id == template.service_id)
        ).all():
            notify_db.session.delete(history)
        template_redacted = notify_db.session.get(TemplateRedacted, template.id)
        notify_db.session.delete(template_redacted)
        notify_db.session.delete(template)
    notify_db.session.commit()


@pytest.fixture(scope='session')
def sample_user_session(notify_db):
    created_user_ids = []

    def _sample_user(*args, **kwargs):
        # Cannot set platform admin when creating a user (schema)
        user = create_user(*args, **kwargs)
        created_user_ids.append(user.id)
        return user

    yield _sample_user

    cleanup_user(created_user_ids, notify_db.session)


def pytest_sessionfinish(session, exitstatus):
    """
    A pytest hook that runs after all tests. Reports database is clear of extra entries after all tests have ran.
    Exit code is set to 1 if anything is left in any table.
    """
    from tests.conftest import application
    from sqlalchemy.sql import text as sa_text
    from time import sleep

    sleep(2)  # Allow fixtures to finish their work

    color = '\033[91m'
    reset = '\033[0m'
    TRUNCATE_ARTIFACTS = True

    with application.app_context():

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=SAWarning)
            meta_data = db.MetaData(bind=db.engine)
            db.MetaData.reflect(meta_data)

        acceptable_counts = {
            'communication_items': 4,
            'job_status': 9,
            'key_types': 3,
            'provider_details': 9,
            'provider_details_history': 9,
            'provider_rates': 5,
            'rates': 2,
            'service_callback_channel': 2,
            'service_callback_type': 3,
            'service_permission_types': 12,
        }

        skip_tables = (
            'alembic_version',
            'auth_type',
            'branding_type',
            'dm_datetime',
            'key_types',
            'notification_status_types',
            'template_process_type',
        )
        to_be_deleted_tables = (
            'organisation_types',
            'letter_rates',
            'invite_status_type',
            'job_status',
        )

        # Gather tablenames & sort
        table_list = sorted([table for table in db.engine.table_names()
                            if table not in skip_tables and table not in to_be_deleted_tables])

        # Use metadata to query the table and add the table name to the list if there are any records
        tables_with_artifacts = []
        for table_name in table_list:
            row_count = len(db.session.execute(select(meta_data.tables[table_name])).all())
            # Only way it's okay to have records is if count <= acceptable count
            if table_name in acceptable_counts and row_count <= acceptable_counts[table_name]:
                continue
            elif row_count > 0:
                tables_with_artifacts.append(table_name)
                session.exitstatus = 1

        if tables_with_artifacts and TRUNCATE_ARTIFACTS:
            print('\n')
            for table in tables_with_artifacts:
                # Skip tables that may have necessary information
                if table not in acceptable_counts:
                    db.session.execute(sa_text(f"""TRUNCATE TABLE {table} CASCADE"""))
                    print(f'Truncating {color}{table}{reset} with cascade...')
                else:
                    print(f'Table {table} contains too many records but {color}cannot be truncated{reset}.')
            db.session.commit()
            print(f"\n\nThese tables contained artifacts: "
                  f"{tables_with_artifacts}\n\n{color}UNIT TESTS FAILED{reset}")
        elif tables_with_artifacts:
            print(f"\n\nThese tables contain artifacts: "
                  f"{color}{tables_with_artifacts}\n\nUNIT TESTS FAILED{reset}")
        else:
            color = '\033[32m'  # Green - pulled out for clarity
            print(f'\n\n{color}DATABASE IS CLEAN{reset}')
