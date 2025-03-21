import pytest
from flask import json

from app.constants import EMAIL_TYPE, SMS_TYPE
from tests import create_authorization_header
from tests.app.conftest import RESTRICTED_TEMPLATE_TYPES

valid_personalisation = {'personalisation': {'Name': 'Jo'}}

valid_post = [
    (
        'Some subject',
        'Some content',
        None,
        'Some subject',
        'Some content',
    ),
    (
        'Some subject',
        'Dear ((Name)), Hello. Yours Truly, The Government.',
        valid_personalisation,
        'Some subject',
        'Dear Jo, Hello. Yours Truly, The Government.',
    ),
    (
        'Message for ((Name))',
        'Dear ((Name)), Hello. Yours Truly, The Government.',
        valid_personalisation,
        'Message for Jo',
        'Dear Jo, Hello. Yours Truly, The Government.',
    ),
    (
        'Message for ((Name))',
        'Some content',
        valid_personalisation,
        'Message for Jo',
        'Some content',
    ),
]


@pytest.mark.parametrize('tmp_type', RESTRICTED_TEMPLATE_TYPES)
@pytest.mark.parametrize('subject,content,post_data,expected_subject,expected_content', valid_post)
def test_valid_post_template_returns_200(
    client,
    sample_api_key,
    sample_template,
    tmp_type,
    subject,
    content,
    post_data,
    expected_subject,
    expected_content,
):
    api_key = sample_api_key()
    template = sample_template(service=api_key.service, template_type=tmp_type, subject=subject, content=content)

    auth_header = create_authorization_header(api_key)

    response = client.post(
        path='/v2/template/{}/preview'.format(template.id),
        data=json.dumps(post_data),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['id'] == str(template.id)

    if tmp_type != SMS_TYPE:
        assert expected_subject in resp_json['subject']

    if tmp_type == EMAIL_TYPE:
        assert expected_content in resp_json['html']
    else:
        assert resp_json['html'] is None

    assert expected_content in resp_json['body']


@pytest.mark.parametrize('tmp_type', RESTRICTED_TEMPLATE_TYPES)
def test_invalid_post_template_returns_400(
    client,
    sample_api_key,
    sample_template,
    tmp_type,
):
    api_key = sample_api_key()
    template = sample_template(
        service=api_key.service,
        template_type=tmp_type,
        content='Dear ((Name)), Hello ((Missing)). Yours Truly, The Government.',
    )

    auth_header = create_authorization_header(api_key)

    response = client.post(
        path='/v2/template/{}/preview'.format(str(template.id)),
        data=json.dumps(valid_personalisation),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 400

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['errors'][0]['error'] == 'BadRequestError'
    assert 'Missing personalisation: Missing' in resp_json['errors'][0]['message']


def test_post_template_with_non_existent_template_id_returns_404(
    client,
    fake_uuid,
    sample_api_key,
):
    auth_header = create_authorization_header(sample_api_key())

    response = client.post(
        path='/v2/template/{}/preview'.format(fake_uuid),
        data=json.dumps(valid_personalisation),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response == {'errors': [{'error': 'NoResultFound', 'message': 'No result found'}], 'status_code': 404}
