""" Implement v3 endpoints for the Notification model. """

from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.notification_schemas import notification_v3_post_request_schema
from flask import Blueprint, request
from jsonschema.validators import Draft202012Validator
from uuid import uuid4

v3_notifications_blueprint = Blueprint("v3_notifications", __name__, url_prefix='/notifications')

# Create an instance of Draft202012Validator to validate post request data.  Unit tests
# should call jsonschema.validate, which also verifies that the schema is valid.
v3_notifications_post_request_validator = Draft202012Validator(notification_v3_post_request_schema)


@v3_notifications_blueprint.route("/email", methods=["POST"], endpoint="v3_notification_email")
@v3_notifications_blueprint.route("/sms", methods=["POST"], endpoint="v3_notification_sms")
def post_notification_v3():
    request_data = request.get_json()
    request_data["notification_type"] = EMAIL_TYPE if request.base_url.endswith("email") else SMS_TYPE

    # This might raise jsonschema.ValidationError, which should trigger an error handler in
    # app/v3/__init__.py that returns a 400 response.
    v3_notifications_post_request_validator.validate(request_data)

    request_data["id"] = str(uuid4())
    # TODO 1361 - Pass the validated request data to Celery by calling apply_async (or something else)

    return {"id": request_data["id"]}, 202


def send_notification_v3(request_data: dict) -> str:
    """
    This function is an internal tool to send notifications without having to make API requests.
    It duplicates the above route handler's code, rather than have the route handler call this
    function, to maximize the efficiency of the route handler, thereby maximizing the throughput
    of notification requests.
    """

    # This might raise jsonschema.ValidationError.  Upstream code should handle this exception.
    v3_notifications_post_request_validator.validate(request_data)

    # This has the side effect of modifying the input in the upstream code.
    request_data["id"] = str(uuid4())

    # TODO 1361 - Pass the validated request data to Celery by calling apply_async (or something else)
    return request_data["id"]
