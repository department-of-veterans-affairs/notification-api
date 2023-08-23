""" Test the schemas for /v3/notifications. """

import pytest
from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.notification_schemas import notification_v3_post_request_schema
from jsonschema import FormatChecker, validate, ValidationError


@pytest.mark.parametrize(
    "post_data, should_validate",
    (
        (
            {
                "notification_type": SMS_TYPE,
                "to": "+12701234567",
                "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            True,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            True,
        ),
        (
            {
                "notification_type": SMS_TYPE,
                "to": "+12701234567",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            False,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "not an e-mail address",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            False,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
                "template_id": "not a UUID4",
            },
            False,
        ),
        (
            {
                "notification_type": SMS_TYPE,
                "recipient_identifier": {
                    "id_type": "VAPROFILEID",
                    "id_value": "some value",
                },
                "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            True,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "recipient_identifier": {
                    "id_type": "EDIPI",
                    "id_value": "some value",
                },
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            True,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "something": 42,
            },
            False,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            False,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
                "recipient_identifier": {
                    "id_type": "EDIPI",
                    "id_value": "some value",
                },
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            True,
        ),
        (
            {
                "notification_type": "some other type",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            False,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "billing_code": "billing code",
                "client_reference": "client reference",
                "email_reply_to_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "personalisation": {
                    "test": {
                        "file": "string",
                        "filename": "file name",
                        "sending_method": "link",
                    },
                },
                "reference": "reference",
            },
            True,
        ),
    ),
    ids=(
        "SMS with phone number",
        "e-mail with e-mail address",
        "SMS without sms_sender_id",
        "bad e-mail address",
        "bad UUID4",
        "SMS with recipient ID",
        "e-mail with recipient ID",
        "additional properties not allowed",
        'neither "to" nor recipient ID',
        '"to" and recipient ID',
        "unrecognized notification type",
        "all optional fields",
    )
)
def test_notification_v3_post_request_schema(post_data: dict, should_validate: bool):
    format_checker = FormatChecker(["email", "uuid"])

    if should_validate:
        validate(post_data, notification_v3_post_request_schema, format_checker=format_checker)
    else:
        with pytest.raises(ValidationError):
            validate(post_data, notification_v3_post_request_schema, format_checker=format_checker)
