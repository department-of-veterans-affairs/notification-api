""" Implement v3 endpoints for the Notification model. """

import phonenumbers
from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.notification_schemas import (
    notification_v3_post_email_request_schema,
    notification_v3_post_sms_request_schema,
)
from flask import Blueprint, request
from jsonschema import FormatChecker
from jsonschema.validators import Draft202012Validator
from uuid import uuid4
from werkzeug.exceptions import BadRequest

v3_notifications_blueprint = Blueprint("v3_notifications", __name__, url_prefix='/notifications')

#########################################################################
# Create instances of Draft202012Validator to validate post request data.
#########################################################################

v3_notifications_post_email_request_validator = Draft202012Validator(
    notification_v3_post_email_request_schema,
    format_checker=FormatChecker(["email", "uuid"])
)

v3_notifications_post_sms_request_validator = Draft202012Validator(
    notification_v3_post_sms_request_schema,
    format_checker=FormatChecker(["uuid"])
)

#########################################################################


@v3_notifications_blueprint.route("/email", methods=["POST"])
def v3_post_notification_email():
    request_data = request.get_json()
    request_data["notification_type"] = EMAIL_TYPE

    # This might raise an exception, which should trigger an error handler that returns a 400 response.
    return {"id": v3_send_notification(request_data)}, 202


@v3_notifications_blueprint.route("/sms", methods=["POST"])
def v3_post_notification_sms():
    request_data = request.get_json()
    request_data["notification_type"] = SMS_TYPE

    try:
        return {"id": v3_send_notification(request_data)}, 202
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError) as e:
        # This should trigger an error handler that returns a 400 response.
        raise BadRequest from e


def v3_send_notification(request_data: dict) -> str:
    """
    This function can be called directly to send notifications without having to make API requests.
    In that use case, the upstream code is responsbile for populating notification_type and for
    catching exceptions.
    """

    # This might raise jsonschema.ValidationError.
    if request_data["notification_type"] == EMAIL_TYPE:
        v3_notifications_post_email_request_validator.validate(request_data)
    elif request_data["notification_type"] == SMS_TYPE:
        v3_notifications_post_sms_request_validator.validate(request_data)
    else:
        raise RuntimeError("Unrecognized notification type.  This is a programming error.")

    if "phone_number" in request_data:
        # This might raise phonenumbers.phonenumberutil.NumberParseException.
        phone_number = phonenumbers.parse(request_data["phone_number"]) 

        # This is a possible phone number, but is it in an assigned exchange (valid area code, etc.)?
        if not phonenumbers.is_valid_number(phone_number):
            raise ValueError(f"{request_data['phone_number']} is not a valid phone number.")

    # This has the side effect of modifying the input in the upstream code.
    request_data["id"] = str(uuid4())

    # TODO 1361 - Pass the validated request data to Celery by calling apply_async (or something else)
    return request_data["id"]
