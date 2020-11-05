import re
import urllib
import uuid
from datetime import datetime
from urllib.parse import urlunsplit

from flask import current_app
import pytest

from app import GovdeliveryClient

from app.models import (
    Notification,
    KEY_TYPE_NORMAL,
    Organisation, Service, User, EMAIL_TYPE, SMS_TYPE, Template
)

import app.googleanalytics.pixels as gapixels


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
        'id': uuid.uuid4(),
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
        smtp_user=None,

):
    service = Service(
        name=service_name,
        message_limit=message_limit,
        restricted=restricted,
        email_from=email_from if email_from else service_name.lower().replace(' ', '.'),
        created_by=user if user else create_user_model(email='{}@mailinator.com'.format(uuid.uuid4())),
        prefix_sms=prefix_sms,
        organisation_type=organisation_type,
        go_live_user=go_live_user,
        go_live_at=go_live_at,
        crown=crown,
        smtp_user=smtp_user,
        organisation=organisation if organisation else Organisation(id=uuid.uuid4(), name='sample organization')
    )
    service.active = active
    service.research_mode = research_mode
    service.count_as_live = count_as_live

    return service


def create_user_model(
        mobile_number="+16502532222",
        email="notify@notify.va.gov",
        state='active',
        id_=None,
        name="Test User",
        blocked=False,
):
    data = {
        'id': id_ or uuid.uuid4(),
        'name': name,
        'email_address': email,
        'password': 'password',
        'mobile_number': mobile_number,
        'state': state,
        'blocked': blocked
    }
    user = User(**data)
    return user


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
):
    created_at = datetime.utcnow()

    if service is None:
        service = create_service_model()

    if template is None:
        template = create_template_model(service=service)

    notification_id = uuid.uuid4()

    if to_field:
        to = to_field
    else:
        to = '+16502532222'

    data = {
        'id': notification_id,
        'to': to,
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
    }
    if job_row_number is not None:
        data['job_row_number'] = job_row_number
    notification = Notification(**data)

    return notification


@pytest.fixture(scope='function')
def govdelivery_client():
    email_client = GovdeliveryClient()
    email_client.init_app(None, None, None)
    return email_client


def test_build_ga_pixel_url_contains_expected_parameters(
        sample_notification_model_with_organization,
        govdelivery_client
):
    img_src_url = gapixels.build_ga_pixel_url(sample_notification_model_with_organization, govdelivery_client)

    assert img_src_url is not None
    all_expected_parameters = [
        't=',
        'tid=',
        'cid=',
        'aip=',
        'ec=',
        'ea=',
        'el=',
        'dp=',
        'dt=',
        'cn=',
        'cs=',
        'cm=',
        'ci='
    ]

    assert all(parameter in img_src_url for parameter in all_expected_parameters)


def test_build_ga_pixel_url_contains_expected_parameters(
        sample_notification_model_with_organization,
        govdelivery_client
):
    img_src_url = gapixels.build_ga_pixel_url(sample_notification_model_with_organization, govdelivery_client)
    img_src_url.startswith( current_app.config['GOOGLE_ANALYTICS_URL'])
    assert True


def test_build_ga_pixel_url_is_escaped(sample_notification_model_with_organization, govdelivery_client):
    escaped_template_name = urllib.parse.quote(sample_notification_model_with_organization.template.name)
    escaped_service_name = urllib.parse.quote(sample_notification_model_with_organization.service.name)
    escaped_organization_name = urllib.parse.quote(sample_notification_model_with_organization.service.organisation.name)
    escaped_subject_name = urllib.parse.quote(sample_notification_model_with_organization.subject)

    img_src_url = gapixels.build_ga_pixel_url(sample_notification_model_with_organization, govdelivery_client)

    ga_tid = current_app.config['GOOGLE_ANALYTICS_TID']
    assert 'v=1' in img_src_url
    assert 't=event' in img_src_url
    assert f"tid={ga_tid}" in img_src_url
    assert f"cid={sample_notification_model_with_organization.id}" in img_src_url
    assert 'aip=1' in img_src_url
    assert 'ec=email' in img_src_url
    assert 'ea=open' in img_src_url
    assert f"el={escaped_template_name}" in img_src_url
    assert \
        f"%2F{escaped_organization_name}" \
        f"%2F{escaped_service_name}" \
        f"%2F{escaped_template_name}" in img_src_url
    assert f"dt={escaped_subject_name}" in img_src_url
    assert f"cn={escaped_template_name}" in img_src_url
    assert f"cs={govdelivery_client.get_name()}" in img_src_url
    assert f"cm=email" in img_src_url
    assert f"ci={sample_notification_model_with_organization.template.id}" in img_src_url
