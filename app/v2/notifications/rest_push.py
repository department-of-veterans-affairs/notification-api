from celery.exceptions import CeleryError
from jsonschema import ValidationError
from kombu.exceptions import OperationalError
from flask import current_app, jsonify, request, Request

from app import authenticated_service, mobile_app_registry
from app.celery.provider_tasks import deliver_push
from app.constants import PUSH_TYPE
from app.mobile_app import DEAFULT_MOBILE_APP_TYPE, MobileAppType
from app.schema_validation import validate
from app.utils import get_public_notify_type_text
from app.v2.errors import BadRequestError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.dataclasses import V2PushPayload
from app.v2.notifications.notification_schemas import push_notification_broadcast_request, push_notification_request


@v2_notification_blueprint.route('/push', methods=['POST'])
def send_push_notification():
    return push_notification_helper(push_notification_request)


@v2_notification_blueprint.route('/push/broadcast', methods=['POST'])
def send_push_broadcast_notification():
    return push_notification_helper(push_notification_broadcast_request)


def push_notification_helper(schema: dict):
    """
    Note that this helper cannot be called other than as part of a request because it accesses
    the Flask "request" instance.
    """
    if not authenticated_service.has_permissions(PUSH_TYPE):
        raise BadRequestError(
            message='Service is not allowed to send {}'.format(
                get_public_notify_type_text(PUSH_TYPE, plural=True),
            ),
            status_code=403,
        )

    payload = validate_push_payload(request, schema)

    try:
        # Choosing to use the email queue for push to limit the number of empty queues
        deliver_push.delay(payload)
    except (CeleryError, OperationalError):
        current_app.logger.exception('Failed to enqueue deliver_push request')
        response = jsonify(result='error', status=502, message='VA Notify service impaired, please try again')
    else:
        response = jsonify(result='success', status=201)

    return response


def validate_push_payload(schema: dict[str, str], request: Request) -> V2PushPayload:
    """Validate an incoming push request.

    Args:
        schema (dict[str, str]): The incoming request

    Raises:
        BadRequestError: Failed validation

    Returns:
        dict[str, str]: Validated request dictionary
    """
    try:
        req_json: dict[str, str] = validate(request.get_json(), schema)

        # Validate the application they sent us is valid or use the default
        if 'mobile_app' in req_json:
            app_sid = mobile_app_registry.get_app(MobileAppType[req_json['mobile_app']]).sid
        else:
            app_sid = mobile_app_registry.get_app(DEAFULT_MOBILE_APP_TYPE).sid
    except (KeyError, TypeError, ValidationError) as e:
        current_app.logger.warning('Push request failed validation: %s', e)
        raise BadRequestError(message=e.message, status_code=400)
    except Exception:
        msg = 'Unable to process request for push notification - bad request'
        current_app.logger.exception(msg)
        raise BadRequestError(message=msg, status_code=400)

    # Use get() on optionals - schema validated it is correct
    payload = V2PushPayload(
        app_sid,
        req_json['template_id'],
        req_json.get('recipient_identifier', {}).get('id_value'),  # ICN
        req_json.get('topic_sid'),
        req_json.get('personalisation'),
    )
    current_app.logger.debug('V2PushPayload: %s', payload)
    return payload
