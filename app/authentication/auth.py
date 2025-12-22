import functools
from datetime import datetime
import hmac
from typing import Callable
from uuid import uuid4
import time
import uuid

from flask import request, current_app, g
from flask_jwt_extended import verify_jwt_in_request, current_user
from flask_jwt_extended.config import config
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from notifications_python_client.authentication import decode_jwt_token, get_token_issuer
from notifications_python_client.errors import TokenError, TokenDecodeError, TokenExpiredError, TokenIssuerError
from notifications_utils import request_helper
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound


from app.dao.services_dao import dao_fetch_service_by_id_with_api_keys
from app.dao.users_dao import get_user_by_id


class AuthError(Exception):
    def __init__(
        self,
        message,
        code,
        service_id=None,
        api_key_id=None,
    ):
        self.message = message
        self.short_message = message
        self.code = code
        self.service_id = service_id
        self.api_key_id = api_key_id

    def __str__(self):
        return 'AuthError({message}, {code}, service_id={service_id}, api_key_id={api_key_id})'.format(**self.__dict__)

    def to_dict_v2(self):
        return {'status_code': self.code, 'errors': [{'error': 'AuthError', 'message': self.short_message}]}

    def to_dict_v3(self):
        """
        All v3 routes use this format for 401 and 403 responses.
        """

        error_message = self.short_message
        if error_message.lower().startswith('invalid token:'):
            error_message = 'Invalid token'

        return {'errors': [{'error': 'AuthError', 'message': error_message}]}


class FirehoseAuthError(Exception):
    def __init__(self, request_id, code):
        super().__init__(f'Firehose auth error: status code {code} for request {request_id}')
        self.request_id = request_id
        self.code = code
        self.timestamp = int(time.time() * 1000)

    def response_body(self):
        return {'requestId': self.request_id, 'timestamp': self.timestamp}


def get_auth_token(req):
    auth_header = req.headers.get('Authorization', None)
    if not auth_header:
        raise AuthError('Unauthorized, authentication token must be provided', 401)

    auth_scheme = auth_header[:7].title()

    if auth_scheme != 'Bearer ':
        raise AuthError('Unauthorized, authentication bearer scheme must be used', 401)

    return auth_header[7:]


def do_not_validate_auth():
    pass


def validate_admin_basic_auth():
    """
    Validate admin access using HTTP Basic Auth.

    Expects:
      - Authorization: Basic base64(user_id:password)
    """
    # Preserve your proxy header checks
    request_helper.check_proxy_header_before_request()

    auth = request.authorization

    # No Authorization header or not Basic
    if not auth or not auth.type or auth.type.lower() != 'basic':
        raise AuthError('Unauthorized, basic authentication required', 401)

    user_id = auth.username
    password = auth.password

    if not user_id or not password:
        raise AuthError('Unauthorized, invalid basic auth credentials', 401)

    try:
        # ensure valid user_id format
        uuid.UUID(user_id, version=4)
    except ValueError:
        raise AuthError('Unauthorized, invalid basic auth credentials', 401)

    try:
        user = get_user_by_id(user_id)
    except NoResultFound:
        raise AuthError('Unauthorized, invalid basic auth credentials', 401)

    if not user.email_address or user.email_address.startswith('_archived_'):
        raise AuthError('Unauthorized, invalid basic auth credentials', 401)

    if not user.check_password(password):
        raise AuthError('Unauthorized, invalid basic auth credentials', 401)

    if not user.platform_admin:
        raise AuthError('Unauthorized, admin authentication required', 401)

    g.admin_user = user_id
    g.service_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')

    current_app.logger.info(
        'API authorized for admin user %s with basic-auth, using client %s',
        user_id,
        request.headers.get('User-Agent'),
    )


def validate_admin_jwt_auth():
    request_helper.check_proxy_header_before_request()

    auth_token = get_auth_token(request)
    client = __get_token_issuer(auth_token)

    if client == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        g.service_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
        handle_admin_key(auth_token, current_app.config.get('ADMIN_CLIENT_SECRET'))
        current_app.logger.info(
            'API authorized for admin with JWT, using client %s',
            request.headers.get('User-Agent'),
        )
        return
    else:
        raise AuthError('Unauthorized, admin authentication token required', 401)


# TODO: API-2651 remove fallback to JWT auth after acceptable grace period
def validate_admin_basic_auth_with_fallback():
    try:
        validate_admin_basic_auth()
    except AuthError:
        current_app.logger.exception(
            'Admin basic-auth failed, attempting jwt fallback, using client %s',
            request.headers.get('User-Agent'),
        )
        validate_admin_jwt_auth()


def create_validator_for_user_in_service_or_admin(required_permission: str = None) -> Callable:
    def _validate_user_in_service_or_platform_admin():
        # when fetching data, the browser may send a pre-flight OPTIONS request.
        # the W3 spec for CORS pre-flight requests states that user credentials should be excluded.
        # hence, for OPTIONS requests, we should skip authentication
        # see https://stackoverflow.com/a/15734032
        if request.method in config.exempt_methods:
            return

        service_id = request.view_args.get('service_id')
        verify_jwt_in_request()

        if not any(service.id == service_id for service in current_user.services) and not current_user.platform_admin:
            raise AuthError('User is not a member of the specified service', 403, service_id=service_id)

        if required_permission and not current_user.platform_admin:
            user_permissions = current_user.get_permissions(service_id)
            if required_permission not in user_permissions:
                raise AuthError(f'User does not have permission {required_permission}', 403, service_id=service_id)

    return _validate_user_in_service_or_platform_admin


def create_validator_for_admin_auth_or_user_in_service(required_permission: str = None) -> Callable:
    def _validate_admin_auth_or_user_in_service():
        try:
            validate = create_validator_for_user_in_service_or_admin(required_permission)
            validate()
        except (JWTExtendedException, PyJWTError, AuthError):
            # TODO: API-2651 remove fallback to JWT auth after acceptable grace period, use validate_admin_basic_auth
            validate_admin_basic_auth_with_fallback()

    return _validate_admin_auth_or_user_in_service


# Allow JWT based admin auth for template preview endpoints used by Portal
def create_validator_for_admin_auth_jwt_or_user_in_service(required_permission: str = None) -> Callable:
    def _validate_admin_auth_jwt_or_user_in_service():
        try:
            validate = create_validator_for_user_in_service_or_admin(required_permission)
            validate()
        except (JWTExtendedException, PyJWTError, AuthError):
            validate_admin_jwt_auth()

    return _validate_admin_auth_jwt_or_user_in_service


# Only new - user scoped JWT tokens
def requires_user_in_service_or_admin(required_permission: str = None):
    def decorator(function):
        @functools.wraps(function)
        def wrapper(
            *args,
            **kwargs,
        ):
            validate = create_validator_for_user_in_service_or_admin(required_permission)
            validate()

            return function(*args, **kwargs)

        return wrapper

    return decorator


# Try new user scoped JWT token or fallback to old admin client credentials auth
def requires_admin_auth_or_user_in_service(required_permission: str = None):
    def decorator(function):
        @functools.wraps(function)
        def wrapper(
            *args,
            **kwargs,
        ):
            validate = create_validator_for_admin_auth_or_user_in_service(required_permission)
            validate()

            return function(*args, **kwargs)

        return wrapper

    return decorator


# Try new user scoped JWT token or fallback to admin client jwt credentials auth
def requires_admin_auth_jwt_or_user_in_service(required_permission: str = None):
    def decorator(function):
        @functools.wraps(function)
        def wrapper(
            *args,
            **kwargs,
        ):
            validate = create_validator_for_admin_auth_jwt_or_user_in_service(required_permission)
            validate()

            return function(*args, **kwargs)

        return wrapper

    return decorator


# Only old - just admin client credentials auth
def requires_admin_jwt_auth():
    def decorator(function):
        @functools.wraps(function)
        def wrapper(
            *args,
            **kwargs,
        ):
            validate_admin_jwt_auth()
            return function(*args, **kwargs)

        return wrapper

    return decorator


def requires_admin_basic_auth():
    def decorator(function):
        @functools.wraps(function)
        def wrapper(
            *args,
            **kwargs,
        ):
            # TODO: API-2651 remove fallback to JWT auth after acceptable grace period, use validate_admin_basic_auth
            validate_admin_basic_auth_with_fallback()
            return function(*args, **kwargs)

        return wrapper

    return decorator


def validate_service_api_key_auth():  # noqa: C901
    # Set the id here for tracking purposes - becomes notification id
    g.request_id = str(uuid4())
    request_helper.check_proxy_header_before_request()
    auth_token = get_auth_token(request)
    client = __get_token_issuer(auth_token)
    data = request.get_json(silent=True) or {}

    try:
        service = dao_fetch_service_by_id_with_api_keys(client)
    except DataError:
        raise AuthError('Invalid token: service id is not the right data type', 403)
    except NoResultFound:
        raise AuthError('Invalid token: service not found', 403)

    if not service.api_keys:
        raise AuthError('Invalid token: service has no API keys', 403, service_id=service.id)

    if not service.active:
        raise AuthError('Invalid token: service is archived', 403, service_id=service.id)

    for api_key in service.api_keys:
        try:
            # This function call could raise a number of exceptions, all of which are subclasses of TokenError.
            # Catch specific exceptions to raise specific error messages.
            decode_jwt_token(auth_token, api_key.secret)
        except TokenExpiredError:
            err_msg = 'Error: Your system clock must be accurate to within 30 seconds'
            raise AuthError(err_msg, 403, service_id=service.id, api_key_id=api_key.id)
        except TokenError:
            continue

        if api_key.revoked:
            raise AuthError('Invalid token: API key revoked', 403, service_id=service.id, api_key_id=api_key.id)

        # Check if API key has expired
        if api_key.expiry_date <= datetime.utcnow():
            raise AuthError('Invalid token: API key expired', 403, service_id=service.id, api_key_id=api_key.id)

        g.service_id = api_key.service_id
        g.api_user = api_key
        g.authenticated_service = service
        current_app.logger.info(
            'API authorised for service %s (%s) with api key %s, using client %s',
            service.id,
            service.name,
            api_key.id,
            request.headers.get('User-Agent'),
            extra={
                'sms_sender_id': data.get('sms_sender_id'),
                'template_id': data.get('template_id'),
            },
        )
        return
    else:
        # service has API keys, but none matching the one the user provided
        raise AuthError('Invalid token: signature, api token not found', 403, service_id=service.id)


def __get_token_issuer(auth_token):
    try:
        client = get_token_issuer(auth_token)
    except TokenIssuerError:
        raise AuthError('Invalid token: iss field not provided', 403)
    except TokenDecodeError:
        raise AuthError('Invalid token: signature, api token is not valid', 403)
    return client


def handle_admin_key(
    auth_token,
    secret,
):
    try:
        decode_jwt_token(auth_token, secret)
    except TokenExpiredError:
        raise AuthError('Invalid token: expired, check that your system clock is accurate', 403)
    except TokenError:
        # TokenError is the base class for token decoding exceptions.
        raise AuthError('Invalid token: signature, api token is not valid', 403)


def validate_pinpoint_firehose_api_key():
    firehose_request_id = request.headers.get('X-Amz-Firehose-Request-Id', None)
    api_key = request.headers.get('X-Amz-Firehose-Access-Key', None)

    if api_key is None:
        current_app.logger.warning('Firehose API key missing - Request ID: %s', firehose_request_id)
        # Return 401 so Firehose will retry with key
        raise FirehoseAuthError(request_id=firehose_request_id, code=401)

    current_app.logger.info('Firehose API key validation request - Request ID: %s', firehose_request_id)

    if not hmac.compare_digest(api_key, current_app.config.get('AWS_PINPOINT_FIREHOSE_API_KEY')):
        current_app.logger.warning('Firehose API key invalid - Request ID: %s', firehose_request_id)
        # Return 403 so Firehose will retry with valid key
        raise FirehoseAuthError(request_id=firehose_request_id, code=403)

    current_app.logger.info('Firehose API key validation successful - Request ID: %s', firehose_request_id)
