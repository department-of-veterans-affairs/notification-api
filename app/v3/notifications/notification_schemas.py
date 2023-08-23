"""
Define schemas to validate requests to /v3/notifications.
https://json-schema.org/understanding-json-schema/
"""

from app.models import EMAIL_TYPE, SMS_TYPE
from app.schema_validation.definitions import personalisation
from app.va.identifier import IdentifierType


# This is copied from v2 so v3 does not depend on any v1 or v2 code.  The long
# term goal is to delete older versions.
recipient_identifier_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "id_type": {
            "type": "string",
            "enum": IdentifierType.values()
        },
        "id_value": {"type": "string"}
    },
    "required": ["id_type", "id_value"]
}


notification_v3_post_request_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "billing_code": {"type": "string", "maxLength": 256},
        "client_reference": {"type": "string"},
        "email_reply_to_id": {"type": "string", "format": "uuid"},
        "notification_type": {"type": "string", "enum": [EMAIL_TYPE, SMS_TYPE]},
        "personalisation": personalisation,
        "recipient_identifier": recipient_identifier_schema,
        "reference": {"type": "string"},
        "sms_sender_id": {"type": "string", "format": "uuid"},
        "template_id": {"type": "string", "format": "uuid"},
        "to": {
            "description": "A phone number or e-mail address",
            "type": "string"
        }
    },
    "additionalProperties": False,
    "required": ["notification_type", "template_id"],
    "anyOf": [
        {"required": ["to"]},
        {"required": ["recipient_identifier"]}
    ],
    "if": {
        "properties": {"notification_type": {"const": SMS_TYPE}}
    },
    "then": {
        # For SMS_TYPE notifications, sms_sender_id is required.
        # Note that there is no "phone_number" string format, contrary to the v2 schema definition.
        "required": ["sms_sender_id"]
    },
    "else": {
        # For EMAIL_TYPE notifications, "to", if present, must have the "email" format.
        "properties": {"to": {"type": "string", "format": "email"}}
    }
}
