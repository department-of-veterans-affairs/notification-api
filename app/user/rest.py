import base64
import json
import uuid
import pickle  # nosec
import pwnedpasswords
import requests
from datetime import datetime, timedelta
from fido2 import cbor
from fido2.webauthn import AuthenticatorData, CollectedClientData
from flask import jsonify, request, Blueprint, current_app, abort
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlencode

from app import db
from app.config import QueueNames, Config
from app.constants import EMAIL_TYPE, HTTP_TIMEOUT, KEY_TYPE_NORMAL, SMS_TYPE
from app.dao.fido2_key_dao import (
    save_fido2_key,
    list_fido2_keys,
    delete_fido2_key,
    decode_and_register,
    create_fido2_session,
    get_fido2_session,
)
from app.dao.login_event_dao import (
    list_login_events,
    save_login_event,
)
from app.dao.users_dao import (
    get_user_by_id,
    save_model_user,
    create_user_code,
    get_user_code,
    use_user_code,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email,
    get_users_by_partial_email,
    create_secret_code,
    save_user_attribute,
    update_user_password,
    count_user_verify_codes,
    get_user_and_accounts,
    dao_archive_user,
    verify_within_time,
)
from app.dao.permissions_dao import permission_dao
from app.dao.service_user_dao import dao_get_service_user, dao_update_service_user
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.template_folder_dao import dao_get_template_folder_by_id_and_service_id
from app.models import Fido2Key, LoginEvent, Permission, Service
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.schemas import (
    email_data_request_schema,
    support_email_data_schema,
    branding_request_data_schema,
    partial_email_data_request_schema,
    create_user_schema,
    user_update_schema_load_json,
    user_update_password_schema_load_json,
)
from app.errors import InvalidRequest, register_errors
from app.schema_validation import validate
from app.user.users_schema import (
    post_verify_code_schema,
    post_send_user_sms_code_schema,
    post_send_user_email_code_schema,
    post_set_permissions_schema,
    fido2_key_schema,
)
from app.utils import update_dct_to_str, url_with_token

user_blueprint = Blueprint('user', __name__)
register_errors(user_blueprint)


@user_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the auth type/mobile number check constraint
    """
    if 'ck_users_mobile_number_if_sms_auth' in str(exc):
        # we don't expect this to trip, so still log error
        current_app.logger.exception('Check constraint ck_users_mobile_number_if_sms_auth triggered')
        return jsonify(result='error', message='Mobile number must be set if auth_type is set to sms_auth'), 400

    raise exc


@user_blueprint.route('', methods=['POST'])
def create_user():
    req_json = request.get_json()
    user_to_create, errors = create_user_schema.load(req_json)
    identity_provider_user_id = req_json.get('identity_provider_user_id')
    password = req_json.get('password')

    # These blocks cover instances of None and the empty string.  Not testing explicitly
    # for "None" is intentional.
    if not password and not identity_provider_user_id:
        errors.update({'password': ['Missing data for required field.']})
        raise InvalidRequest(errors, status_code=400)
    elif password:
        response = pwnedpasswords.check(password)
        if response > 0:
            errors.update({'password': ['Password is blacklisted.']})
            raise InvalidRequest(errors, status_code=400)

    save_model_user(user_to_create, pwd=password)
    result = user_to_create.serialize()
    return jsonify(data=result), 201


@user_blueprint.route('/<uuid:user_id>', methods=['POST'])
def update_user_attribute(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    if 'updated_by' in req_json:
        updated_by = get_user_by_id(user_id=req_json.pop('updated_by'))
    else:
        updated_by = None

    update_dct, errors = user_update_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    save_user_attribute(user_to_update, update_dict=update_dct)

    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    # Alert user that account change took place
    change_type = update_dct_to_str(update_dct)
    _update_alert(user_to_update, change_type)

    # Alert that team member edit user
    if updated_by:
        if 'email_address' in update_dct:
            template = dao_get_template_by_id(current_app.config['TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID'])
            recipient = user_to_update.email_address
            reply_to = None
        elif 'mobile_number' in update_dct:
            template = dao_get_template_by_id(current_app.config['TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID'])
            recipient = user_to_update.mobile_number
            reply_to = template.service.get_default_sms_sender()
        else:
            return jsonify(data=user_to_update.serialize()), 200

        saved_notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=recipient,
            service_id=service.id,
            personalisation={
                'name': user_to_update.name,
                'servicemanagername': updated_by.name,
                'email address': user_to_update.email_address,
                'change_type': change_type,
            },
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            reply_to_text=reply_to,
        )

        send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/archive', methods=['POST'])
def archive_user(user_id):
    user = get_user_by_id(user_id)
    dao_archive_user(user)

    return '', 204


@user_blueprint.route('/<uuid:user_id>/activate', methods=['POST'])
def activate_user(user_id):
    user = get_user_by_id(user_id=user_id)
    if user.state == 'active':
        raise InvalidRequest('User already active', status_code=400)

    user.state = 'active'
    save_model_user(user)
    return jsonify(data=user.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/reset-failed-login-count', methods=['POST'])
def user_reset_failed_login_count(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    reset_failed_login_count(user_to_update)
    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    user_to_verify = get_user_by_id(user_id=user_id)
    data = request.get_json()

    try:
        txt_pwd = data['password']
    except KeyError:
        message = 'Required field missing data'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)

    if user_to_verify.check_password(txt_pwd):
        reset_failed_login_count(user_to_verify)
        if 'loginData' in data and data['loginData'] != {}:
            save_login_event(LoginEvent(user_id=user_id, data=data['loginData']))
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        message = 'Incorrect password'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)


@user_blueprint.route('/<uuid:user_id>/verify/code', methods=['POST'])
def verify_user_code(user_id):
    data = request.get_json()
    validate(data, post_verify_code_schema)

    user_to_verify = get_user_by_id(user_id=user_id)

    code = get_user_code(user_to_verify, data['code'], data['code_type'])

    if verify_within_time(user_to_verify) >= 2:
        raise InvalidRequest('Code already sent', status_code=400)

    if user_to_verify.failed_login_count >= current_app.config.get('MAX_VERIFY_CODE_COUNT'):
        raise InvalidRequest('Code not found', status_code=404)
    if not code:
        # only relevant from sms
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest('Code not found', status_code=404)
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        # sms and email
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest('Code has expired', status_code=400)

    user_to_verify.current_session_id = str(uuid.uuid4())
    user_to_verify.logged_in_at = datetime.utcnow()
    user_to_verify.failed_login_count = 0
    save_model_user(user_to_verify)

    use_user_code(code.id)
    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/<code_type>-code', methods=['POST'])
def send_user_2fa_code(
    user_id,
    code_type,
):
    user_to_send_to = get_user_by_id(user_id=user_id)

    if verify_within_time(user_to_send_to, age=timedelta(seconds=10)) >= 1:
        raise InvalidRequest('Code already sent, wait 10 seconds', status_code=400)

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get('MAX_VERIFY_CODE_COUNT'):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warning('Too many verify codes created for user %s', user_to_send_to.id)
    else:
        data = request.get_json()
        if code_type == SMS_TYPE:
            validate(data, post_send_user_sms_code_schema)
            send_user_sms_code(user_to_send_to, data)
        elif code_type == EMAIL_TYPE:
            validate(data, post_send_user_email_code_schema)
            send_user_email_code(user_to_send_to, data)
        else:
            abort(404)

    return '{}', 204


def send_user_sms_code(
    user_to_send_to,
    data,
):
    recipient = data.get('to') or user_to_send_to.mobile_number

    secret_code = create_secret_code()
    personalisation = {'verify_code': secret_code}

    create_2fa_code(
        current_app.config['SMS_CODE_TEMPLATE_ID'], user_to_send_to, secret_code, recipient, personalisation
    )


def send_user_email_code(
    user_to_send_to,
    data,
):
    recipient = user_to_send_to.email_address

    secret_code = str(uuid.uuid4())
    personalisation = {
        'name': user_to_send_to.name,
        'url': _create_2fa_url(user_to_send_to, secret_code, data.get('next'), data.get('email_auth_link_host')),
    }

    create_2fa_code(
        current_app.config['EMAIL_2FA_TEMPLATE_ID'], user_to_send_to, secret_code, recipient, personalisation
    )


def create_2fa_code(
    template_id,
    user_to_send_to,
    secret_code,
    recipient,
    personalisation,
):
    template = dao_get_template_by_id(template_id)

    # save the code in the VerifyCode table
    create_user_code(user_to_send_to, secret_code, template.template_type)
    reply_to = None

    if template.template_type == SMS_TYPE:
        reply_to = template.service.get_default_sms_sender()

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=recipient,
        service_id=template.service.id,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=reply_to,
    )
    # Assume that we never want to observe the Notify service's research mode
    # setting for this notification - we still need to be able to log into the
    # admin even if we're doing user research using this service:
    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)


@user_blueprint.route('/<uuid:user_id>/change-email-verification', methods=['POST'])
def send_user_confirm_new_email(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    email, errors = email_data_request_schema.load(request.get_json())
    if errors:
        raise InvalidRequest(message=errors, status_code=400)

    template = dao_get_template_by_id(current_app.config['CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=email['email'],
        service_id=service.id,
        personalisation={
            'name': user_to_send_to.name,
            'url': _create_confirmation_url(user=user_to_send_to, email_address=email['email']),
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/support',
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)
    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/email-verification', methods=['POST'])
def send_new_user_email_verification(user_id):
    # when registering, we verify all users' email addresses using this function
    user_to_send_to = get_user_by_id(user_id=user_id)

    template = dao_get_template_by_id(current_app.config['NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=user_to_send_to.email_address,
        service_id=service.id,
        personalisation={'name': user_to_send_to.name, 'url': _create_verification_url(user_to_send_to)},
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/email-already-registered', methods=['POST'])
def send_already_registered_email(user_id):
    to, errors = email_data_request_schema.load(request.get_json())
    template = dao_get_template_by_id(current_app.config['ALREADY_REGISTERED_EMAIL_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=to['email'],
        service_id=service.id,
        personalisation={
            'signin_url': current_app.config['ADMIN_BASE_URL'] + '/sign-in',
            'forgot_password_url': current_app.config['ADMIN_BASE_URL'] + '/forgot-password',
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/support',
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/support-email', methods=['POST'])
def send_support_email(user_id):
    data, errors = support_email_data_schema.load(request.get_json())

    API_URL = current_app.config['FRESH_DESK_API_URL']
    API_KEY = current_app.config['FRESH_DESK_API_KEY']

    ticket = {
        'product_id': 61000000046,
        'subject': data['support_type'] if 'support_type' in data else 'Support Request',
        'description': data['message'],
        'email': data['email'],
        'priority': 1,
        'status': 2,
    }

    response = requests.post(
        '{}/api/v2/tickets'.format(API_URL),
        json=ticket,
        auth=requests.HTTPBasicAuth(API_KEY, 'x'),
        timeout=HTTP_TIMEOUT,
    )

    if response.status_code != 201:
        print('Failed to create ticket, errors are displayed below')
        content = json.loads(response.content)
        print(content['errors'])
        print('x-request-id : {}'.format(content.headers['x-request-id']))
        print('Status Code : {}'.format(str(content.status_code)))

    return jsonify({'status_code': response.status_code}), 204


@user_blueprint.route('/<uuid:user_id>/branding-request', methods=['POST'])
def send_branding_request(user_id):
    to, errors = branding_request_data_schema.load(request.get_json())
    template = dao_get_template_by_id(current_app.config['BRANDING_REQUEST_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=to['email'],
        service_id=service.id,
        personalisation={
            'email': to['email'],
            'serviceID': to['serviceID'],
            'service_name': to['service_name'],
            'filename': to['filename'],
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )
    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>', methods=['GET'])
@user_blueprint.route('', methods=['GET'])
def get_user(user_id=None):
    users = get_user_by_id(user_id=user_id)
    result = [x.serialize() for x in users] if isinstance(users, list) else users.serialize()
    return jsonify(data=result)


@user_blueprint.route('/<uuid:user_id>/service/<uuid:service_id>/permission', methods=['POST'])
def set_permissions(
    user_id,
    service_id,
):
    """This route requires admin authorization.  This is setup in app/__init__.py."""

    service_user = dao_get_service_user(user_id, service_id)
    user = service_user.user
    service = dao_fetch_service_by_id(service_id=service_id)

    data = request.get_json()
    validate(data, post_set_permissions_schema)

    permission_list = [
        Permission(service_id=service_id, user_id=user_id, permission=p['permission']) for p in data['permissions']
    ]

    service_key = 'service_id_{}'.format(service_id)
    change_dict = {service_key: service_id, 'permissions': permission_list}

    try:
        _update_alert(user, update_dct_to_str(change_dict))
    except Exception as e:
        current_app.logger.exception(e)

    permission_dao.set_user_service_permission(user, service, permission_list, _commit=True, replace=True)

    if 'folder_permissions' in data:
        folders = [
            dao_get_template_folder_by_id_and_service_id(folder_id, service_id)
            for folder_id in data['folder_permissions']
        ]

        service_user.folders = folders
        dao_update_service_user(service_user)

    return jsonify({}), 204


@user_blueprint.route('/email', methods=['GET'])
def get_by_email():
    email = request.args.get('email')
    if not email:
        error = 'Invalid request. Email query string param required'
        raise InvalidRequest(error, status_code=400)
    fetched_user = get_user_by_email(email)
    result = fetched_user.serialize()
    return jsonify(data=result)


@user_blueprint.route('/find-users-by-email', methods=['POST'])
def find_users_by_email():
    email, errors = partial_email_data_request_schema.load(request.get_json())
    fetched_users = get_users_by_partial_email(email['email'])
    result = [user.serialize_for_users_list() for user in fetched_users]
    return jsonify(data=result), 200


@user_blueprint.route('/reset-password', methods=['POST'])
def send_user_reset_password():
    email, errors = email_data_request_schema.load(request.get_json())

    user_to_send_to = get_user_by_email(email['email'])

    template = dao_get_template_by_id(current_app.config['PASSWORD_RESET_TEMPLATE_ID'])
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=email['email'],
        service_id=service.id,
        personalisation={
            'user_name': user_to_send_to.name,
            'url': _create_reset_password_url(user_to_send_to.email_address),
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/update-password', methods=['POST'])
def update_password(user_id):
    user = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    pwd = req_json.get('_password')
    update_dct, errors = user_update_password_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    response = pwnedpasswords.check(pwd)
    if response > 0:
        errors.update({'password': ['Password is blacklisted.']})
        raise InvalidRequest(errors, status_code=400)

    update_user_password(user, pwd)
    change_type = update_dct_to_str({'password': 'password updated'})

    try:
        _update_alert(user, change_type)
    except Exception as e:
        current_app.logger.exception(e)

    return jsonify(data=user.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/organisations-and-services', methods=['GET'])
def get_organisations_and_services_for_user(user_id):
    user = get_user_and_accounts(user_id)
    data = get_orgs_and_services(user)
    return jsonify(data)


@user_blueprint.route('/<uuid:user_id>/fido2_keys', methods=['GET'])
def list_fido2_keys_user(user_id):
    data = list_fido2_keys(user_id)
    return jsonify(list(map(lambda o: o.serialize(), data)))


@user_blueprint.route('/<uuid:user_id>/fido2_keys', methods=['POST'])
def create_fido2_keys_user(user_id):
    user = get_user_and_accounts(user_id)
    data = request.get_json()
    cbor_data = cbor.decode(base64.b64decode(data['payload']))
    validate(data, fido2_key_schema)

    id = uuid.uuid4()
    key = decode_and_register(cbor_data, get_fido2_session(user_id))
    save_fido2_key(Fido2Key(id=id, user_id=user_id, name=cbor_data['name'], key=key))
    _update_alert(user)
    return jsonify({'id': id})


@user_blueprint.route('/<uuid:user_id>/fido2_keys/register', methods=['POST'])
def fido2_keys_user_register(user_id):
    user = get_user_and_accounts(user_id)
    keys = list_fido2_keys(user_id)

    # It is safe to do pickle.loads as we ensure the data represents FIDO key when storing
    credentials = list(map(lambda k: pickle.loads(base64.b64decode(k.key)), keys))  # nosec

    registration_data, state = Config.FIDO2_SERVER.register_begin(
        {
            'id': user.id.bytes,
            'name': user.name,
            'displayName': user.name,
        },
        credentials,
        user_verification='discouraged',
    )
    create_fido2_session(user_id, state)

    # API Client only like JSON
    return jsonify({'data': base64.b64encode(cbor.encode(registration_data)).decode('utf8')})


@user_blueprint.route('/<uuid:user_id>/fido2_keys/authenticate', methods=['POST'])
def fido2_keys_user_authenticate(user_id):
    keys = list_fido2_keys(user_id)

    # It is safe to do pickle.loads as we ensure the data represents FIDO key when storing
    credentials = list(map(lambda k: pickle.loads(base64.b64decode(k.key)), keys))  # nosec

    auth_data, state = Config.FIDO2_SERVER.authenticate_begin(credentials)
    create_fido2_session(user_id, state)

    # API Client only like JSON
    return jsonify({'data': base64.b64encode(cbor.encode(auth_data)).decode('utf8')})


@user_blueprint.route('/<uuid:user_id>/fido2_keys/validate', methods=['POST'])
def fido2_keys_user_validate(user_id):
    keys = list_fido2_keys(user_id)

    # It is safe to do pickle.loads as we ensure the data represents FIDO key when storing
    credentials = list(map(lambda k: pickle.loads(base64.b64decode(k.key)), keys))  # nosec

    data = request.get_json()
    cbor_data = cbor.decode(base64.b64decode(data['payload']))

    credential_id = cbor_data['credentialId']
    client_data = CollectedClientData(cbor_data['clientDataJSON'])
    auth_data = AuthenticatorData(cbor_data['authenticatorData'])
    signature = cbor_data['signature']

    Config.FIDO2_SERVER.authenticate_complete(
        get_fido2_session(user_id), credentials, credential_id, client_data, auth_data, signature
    )

    user_to_verify = get_user_by_id(user_id=user_id)
    user_to_verify.current_session_id = str(uuid.uuid4())
    user_to_verify.logged_in_at = datetime.utcnow()
    user_to_verify.failed_login_count = 0
    save_model_user(user_to_verify)

    return jsonify({'status': 'OK'})


@user_blueprint.route('/<uuid:user_id>/fido2_keys/<uuid:key_id>', methods=['DELETE'])
def delete_fido2_keys_user(
    user_id,
    key_id,
):
    user = get_user_and_accounts(user_id)
    delete_fido2_key(user_id, key_id)
    _update_alert(user)
    return jsonify({'id': key_id})


@user_blueprint.route('/<uuid:user_id>/login_events', methods=['GET'])
def list_login_events_user(user_id):
    data = list_login_events(user_id)
    return jsonify(list(map(lambda o: o.serialize(), data)))


def _create_reset_password_url(email):
    data = json.dumps({'email': email, 'created_at': str(datetime.utcnow())})
    url = '/new-password/'
    return url_with_token(data, url, current_app.config)


def _create_verification_url(user):
    data = json.dumps({'user_id': str(user.id), 'email': user.email_address})
    url = '/verify-email/'
    return url_with_token(data, url, current_app.config)


def _create_confirmation_url(
    user,
    email_address,
):
    data = json.dumps({'user_id': str(user.id), 'email': email_address})
    url = '/user-profile/email/confirm/'
    return url_with_token(data, url, current_app.config)


def _create_2fa_url(
    user,
    secret_code,
    next_redir,
    email_auth_link_host,
):
    data = json.dumps({'user_id': str(user.id), 'secret_code': secret_code})
    url = '/email-auth/'
    ret = url_with_token(data, url, current_app.config, base_url=email_auth_link_host)
    if next_redir:
        ret += '?{}'.format(urlencode({'next': next_redir}))
    return ret


def get_orgs_and_services(user):
    return {
        'organisations': [
            {
                'name': org.name,
                'id': org.id,
                'count_of_live_services': len(org.live_services),
            }
            for org in user.organisations
            if org.active
        ],
        'services': [
            {
                'id': service.id,
                'name': service.name,
                'restricted': service.restricted,
                'organisation': service.organisation.id if service.organisation else None,
            }
            for service in user.services
            if service.active
        ],
    }


def _update_alert(
    user_to_update,
    change_type='',
):
    service = db.session.get(Service, current_app.config['NOTIFY_SERVICE_ID'])
    template = dao_get_template_by_id(current_app.config['ACCOUNT_CHANGE_TEMPLATE_ID'])
    recipient = user_to_update.email_address

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=recipient,
        service_id=service.id,
        personalisation={
            'base_url': Config.ADMIN_BASE_URL,
            'contact_us_url': f'{Config.ADMIN_BASE_URL}/support/ask-question-give-feedback',
            'change_type': change_type,
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)
