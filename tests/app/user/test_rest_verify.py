import json
import uuid
from datetime import datetime, timedelta

import pytest
from flask import url_for, current_app
from freezegun import freeze_time

from app.dao.login_event_dao import list_login_events
from app.dao.users_dao import create_user_code
from app.dao.services_dao import dao_update_service, dao_fetch_service_by_id
from app.models import Notification, VerifyCode, EMAIL_TYPE, SMS_TYPE
from app.model import User
from app import db

from tests import create_admin_authorization_header


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01T12:00:00')
def test_user_verify_sms_code(client, sample_sms_code):
    sample_sms_code.user.logged_in_at = datetime.utcnow() - timedelta(days=1)
    assert not VerifyCode.query.first().code_used
    assert sample_sms_code.user.current_session_id is None
    data = json.dumps({'code_type': sample_sms_code.code_type, 'code': sample_sms_code.txt_code})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 204
    assert VerifyCode.query.first().code_used
    assert sample_sms_code.user.logged_in_at == datetime.utcnow()
    assert sample_sms_code.user.current_session_id is not None


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_code_missing_code(client, sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({'code_type': sample_sms_code.code_type})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 400
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 0


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_code_bad_code_and_increments_failed_login_count(client, sample_sms_code):
    assert not VerifyCode.query.first().code_used
    data = json.dumps({'code_type': sample_sms_code.code_type, 'code': 'blah'})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 404
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 1


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_code_expired_code_and_increments_failed_login_count(client, sample_sms_code):
    assert not VerifyCode.query.first().code_used
    sample_sms_code.expiry_datetime = datetime.utcnow() - timedelta(hours=1)
    db.session.add(sample_sms_code)
    db.session.commit()
    data = json.dumps({'code_type': sample_sms_code.code_type, 'code': sample_sms_code.txt_code})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 400
    assert not VerifyCode.query.first().code_used
    assert User.query.get(sample_sms_code.user.id).failed_login_count == 1


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01 10:00:00.000000')
def test_user_verify_password(client, sample_user):
    yesterday = datetime.utcnow() - timedelta(days=1)
    sample_user.logged_in_at = yesterday
    data = json.dumps({'password': 'password'})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 204
    assert User.query.get(sample_user.id).logged_in_at == yesterday


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01T12:00:00')
def test_user_verify_password_creates_login_event(client, sample_user):
    yesterday = datetime.utcnow() - timedelta(days=1)
    sample_user.logged_in_at = yesterday
    data = json.dumps({'password': 'password', 'loginData': {'foo': 'bar'}})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 204
    assert User.query.get(sample_user.id).logged_in_at == yesterday

    events = list_login_events(sample_user.id)
    assert len(events) == 1


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_password_invalid_password(client, sample_user):
    data = json.dumps({'password': 'bad password'})
    auth_header = create_admin_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Incorrect password' in json_resp['message']['password']
    assert sample_user.failed_login_count == 1


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_password_valid_password_resets_failed_logins(client, sample_user):
    data = json.dumps({'password': 'bad password'})
    auth_header = create_admin_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Incorrect password' in json_resp['message']['password']

    assert sample_user.failed_login_count == 1

    data = json.dumps({'password': 'password'})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert resp.status_code == 204
    assert sample_user.failed_login_count == 0


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_password_missing_password(client, sample_user):
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.verify_user_password', user_id=sample_user.id),
        data=json.dumps({'bingo': 'bongo'}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert 'Required field missing data' in json_resp['message']['password']


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@pytest.mark.parametrize('research_mode', [True, False])
@freeze_time('2016-01-01 11:09:00.061258')
def test_send_user_sms_code(client, sample_user, sms_code_template, mocker, research_mode):
    """
    Tests POST endpoint /user/<user_id>/sms-code
    """
    notify_service = dao_fetch_service_by_id(current_app.config['NOTIFY_SERVICE_ID'])
    if research_mode:
        notify_service.research_mode = True
        dao_update_service(notify_service)

    auth_header = create_admin_authorization_header()
    mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
    mocked_task = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=sample_user.id),
        data=json.dumps({}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 204

    mocked.assert_called_once()
    assert VerifyCode.query.one().check_code('11111')

    notification = Notification.query.one()
    assert notification.personalisation == {'verify_code': '11111'}
    assert notification.to == sample_user.mobile_number
    assert str(notification.service_id) == current_app.config['NOTIFY_SERVICE_ID']
    assert notification.reply_to_text == notify_service.get_default_sms_sender()

    result_notification_id, result_queue = mocked_task.call_args
    result_id, *rest = result_notification_id[0]
    assert result_id == str(notification.id)

    assert result_queue['queue'] == 'notify-internal-tasks'
    mocked_task.assert_called_once()


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01 11:09:00.061258')
def test_send_user_code_for_sms_with_optional_to_field(client, sample_user, sms_code_template, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code with optional to field
    """
    to_number = '+447119876757'
    mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
    mocked_task = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    auth_header = create_admin_authorization_header()

    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=sample_user.id),
        data=json.dumps({'to': to_number}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert resp.status_code == 204
    mocked.assert_called_once()
    notification = Notification.query.first()
    assert notification.to == to_number

    result_notification_id, result_queue = mocked_task.call_args
    result_id, *rest = result_notification_id[0]
    assert result_id == str(notification.id)

    assert result_queue['queue'] == 'notify-internal-tasks'
    mocked_task.assert_called_once()


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01 11:09:00.061258')
def test_send_user_code_for_sms_respects_a_retry_time_delta(client, sample_user, sms_code_template, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code will fail if there already is a code with a time delta
    """
    to_number = '+447119876757'
    mocked = mocker.patch('app.user.rest.create_secret_code', return_value='11111')
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    auth_header = create_admin_authorization_header()

    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=sample_user.id),
        data=json.dumps({'to': to_number}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert resp.status_code == 204
    assert mocked.call_count == 1

    # Inside delta
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=sample_user.id),
        data=json.dumps({'to': to_number}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert resp.status_code == 400
    assert mocked.call_count == 1


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_sms_code_returns_404_for_bad_input_data(client):
    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=uuid_),
        data=json.dumps({}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_sms_code_returns_204_when_too_many_codes_already_created(client, sample_user):
    for i in range(10):
        verify_code = VerifyCode(
            code_type=SMS_TYPE,
            _code=12345,
            created_at=datetime.utcnow() - timedelta(minutes=10),
            expiry_datetime=datetime.utcnow() + timedelta(minutes=40),
            user=sample_user,
        )
        db.session.add(verify_code)
        db.session.commit()
    assert VerifyCode.query.count() == 10
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.send_user_2fa_code', code_type=SMS_TYPE, user_id=sample_user.id),
        data=json.dumps({}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 204
    assert VerifyCode.query.count() == 10


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_new_user_email_verification(client, sample_user, mocker, email_verification_template):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.send_new_user_email_verification', user_id=str(sample_user.id)),
        data=json.dumps({}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    notify_service = email_verification_template.service
    assert resp.status_code == 204
    notification = Notification.query.first()
    assert VerifyCode.query.count() == 0

    result_notification_id, result_queue = mocked.call_args
    result_id, *rest = result_notification_id[0]
    assert result_id == str(notification.id)

    assert result_queue['queue'] == 'notify-internal-tasks'
    mocked.assert_called_once()

    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_email_verification_returns_404_for_bad_input_data(client, notify_db_session, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for('user.send_new_user_email_verification', user_id=uuid_),
        data=json.dumps({}),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'
    assert mocked.call_count == 0


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_user_code_returns_404_when_code_is_right_but_user_account_is_locked(client, sample_sms_code):
    sample_sms_code.user.failed_login_count = 10
    data = json.dumps({'code_type': sample_sms_code.code_type, 'code': sample_sms_code.txt_code})
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), create_admin_authorization_header()],
    )
    assert resp.status_code == 404
    assert sample_sms_code.user.failed_login_count == 10
    assert not sample_sms_code.code_used


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_verify_user_code_valid_code_resets_failed_login_count(client, sample_sms_code):
    sample_sms_code.user.failed_login_count = 1
    data = json.dumps({'code_type': sample_sms_code.code_type, 'code': sample_sms_code.txt_code})
    resp = client.post(
        url_for('user.verify_user_code', user_id=sample_sms_code.user.id),
        data=data,
        headers=[('Content-Type', 'application/json'), create_admin_authorization_header()],
    )
    assert resp.status_code == 204
    assert sample_sms_code.user.failed_login_count == 0
    assert sample_sms_code.code_used


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_user_reset_failed_login_count_returns_200(client, sample_user):
    sample_user.failed_login_count = 1
    resp = client.post(
        url_for('user.user_reset_failed_login_count', user_id=sample_user.id),
        data={},
        headers=[('Content-Type', 'application/json'), create_admin_authorization_header()],
    )
    assert resp.status_code == 200
    assert sample_user.failed_login_count == 0


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_reset_failed_login_count_returns_404_when_user_does_not_exist(client):
    resp = client.post(
        url_for('user.user_reset_failed_login_count', user_id=uuid.uuid4()),
        data={},
        headers=[('Content-Type', 'application/json'), create_admin_authorization_header()],
    )
    assert resp.status_code == 404


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@pytest.mark.parametrize(
    'data, expected_auth_url',
    [
        (
            {},
            'http://localhost:6012/email-auth/%2E',
        ),
        (
            {'to': None},
            'http://localhost:6012/email-auth/%2E',
        ),
        (
            {'to': None, 'email_auth_link_host': 'https://example.com'},
            'https://example.com/email-auth/%2E',
        ),
    ],
)
def test_send_user_email_code(
    admin_request,
    mocker,
    sample_user,
    email_2fa_code_template,
    data,
    expected_auth_url,
):
    deliver_email = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    admin_request.post(
        'user.send_user_2fa_code', code_type=EMAIL_TYPE, user_id=sample_user.id, _data=data, _expected_status=204
    )
    notification = Notification.query.one()
    assert notification.reply_to_text == email_2fa_code_template.service.get_default_reply_to_email_address()
    assert notification.to == sample_user.email_address
    assert str(notification.template_id) == current_app.config['EMAIL_2FA_TEMPLATE_ID']
    assert notification.personalisation['name'] == 'Test User'
    assert notification.personalisation['url'].startswith(expected_auth_url)

    result_notification_id, result_queue = deliver_email.call_args
    result_id, *rest = result_notification_id[0]
    assert result_id == str(notification.id)

    assert result_queue['queue'] == 'notify-internal-tasks'
    deliver_email.assert_called_once()


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_user_email_code_with_urlencoded_next_param(admin_request, mocker, sample_user, email_2fa_code_template):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    data = {'to': None, 'next': '/services'}
    admin_request.post(
        'user.send_user_2fa_code', code_type=EMAIL_TYPE, user_id=sample_user.id, _data=data, _expected_status=204
    )
    noti = Notification.query.one()
    assert noti.personalisation['url'].endswith('?next=%2Fservices')


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
def test_send_email_code_returns_404_for_bad_input_data(admin_request):
    resp = admin_request.post(
        'user.send_user_2fa_code', code_type=EMAIL_TYPE, user_id=uuid.uuid4(), _data={}, _expected_status=404
    )
    assert resp['message'] == 'No result found'


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@freeze_time('2016-01-01T12:00:00')
def test_user_verify_email_code(admin_request, sample_user):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, EMAIL_TYPE)

    data = {'code_type': EMAIL_TYPE, 'code': magic_code}

    admin_request.post('user.verify_user_code', user_id=sample_user.id, _data=data, _expected_status=204)

    assert verify_code.code_used
    assert sample_user.logged_in_at == datetime.utcnow()
    assert sample_user.current_session_id is not None


@pytest.mark.skip(reason='Endpoint slated for removal. Test not updated.')
@pytest.mark.parametrize('code_type', [EMAIL_TYPE, SMS_TYPE])
@freeze_time('2016-01-01T12:00:00')
def test_user_verify_email_code_fails_if_code_already_used(admin_request, sample_user, code_type):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, code_type)
    verify_code.code_used = True

    data = {'code_type': code_type, 'code': magic_code}

    admin_request.post('user.verify_user_code', user_id=sample_user.id, _data=data, _expected_status=400)

    assert verify_code.code_used
    assert sample_user.logged_in_at is None
    assert sample_user.current_session_id is None
