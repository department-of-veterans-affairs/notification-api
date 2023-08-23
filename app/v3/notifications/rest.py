""" Implement endpoints for the Notification model. """

from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.notification_schemas import notification_v3_post_request_schema
from flask import Blueprint, request
from jsonschema import FormatChecker, validate, ValidationError
from uuid import uuid4

v3_notifications_blueprint = Blueprint("v3_notifications", __name__, url_prefix='/v3/notifications')


@v3_notifications_blueprint.route("/email", methods=["POST"])
def post_notification_email():
    request_data = request.get_json()
    request_data["notification_type"] = EMAIL_TYPE
    return post_notification(request_data)


@v3_notifications_blueprint.route("/sms", methods=["POST"])
def post_notification_sms():
    request_data = request.get_json()
    request_data["notification_type"] = SMS_TYPE
    return post_notification(request_data)


def post_notification(request_data):
    format_checker = FormatChecker(["email", "uuid"])

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

    return {"uuid": request_data["id"]}, 202
