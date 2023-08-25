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

    # This has the side effect of adding an "id" attribute.
    post_notification_v3_validate_and_send_to_celery(request_data)

    return {"id": request_data["id"]}, 202


def post_notification_v3_validate_and_send_to_celery(request_data):
    """
    Having this as a standalone function provides an internal tool to send messages without having
    to make API requests.
    """

    # This might raise jsonschema.ValidationError.  When this function is called from above, this
    # should trigger an error handler in app/v3/__init__.py that returns a 400 response.  When
    # this function is called other than for an API call, the upstream code should handle this
    # exception.
    v3_notifications_post_request_validator.validate(request_data)

    request_data["id"] = uuid4()
    # TODO 1361 - Pass the validated request data to Celery by calling apply_async (or something else)
