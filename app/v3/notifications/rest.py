""" Implement v3 endpoints for the Notification model. """

from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.notification_schemas import notification_v3_post_request_schema
from flask import Blueprint, request
from jsonschema import FormatChecker, validate, ValidationError
from uuid import uuid4

v3_notifications_blueprint = Blueprint("v3_notifications", __name__, url_prefix='/notifications')


@v3_notifications_blueprint.route("/email", methods=["POST"])
@v3_notifications_blueprint.route("/sms", methods=["POST"])
def post_notification_v3():
    print("MADE IT HERE")
    # TODO 1360 - Make this and a validator module variables so the schema itself isn't checked with
    # every call to "validate".
    format_checker = FormatChecker(["email", "uuid"])

    request_data = request.get_json()
    request_data["notification_type"] = EMAIL_TYPE if request.base_url.endswith("email") else SMS_TYPE

    # TODO 1360 - Let the error handler catch this
    try:
        validate(request_data, notification_v3_post_request_schema, format_checker=format_checker)
    except ValidationError as e:
        return {
            "errors": [
                {
                    "error": "ValidationError",
                    "message": e.message,
                }
            ]
        }, 400

    request_data["id"] = uuid4()
    # TODO 1361 - Pass the validated request data to Celery.

    return {"id": request_data["id"]}, 202
