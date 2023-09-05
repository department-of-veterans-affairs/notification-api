""" Test endpoints for the v3 notifications. """

import pytest
from app.models import EMAIL_TYPE, SMS_TYPE
from app.v3.notifications.rest import v3_send_notification
from flask import url_for
from json import dumps
from jsonschema import ValidationError
from tests import create_authorization_header
from uuid import UUID


@pytest.mark.parametrize(
    "request_data, expected_status_code",
    (
        (
            {
                "notification_type": SMS_TYPE,
                "phone_number": "+18006982411",
                "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            202,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "email_address": "test@va.gov",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            202,
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
            202,
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
            202,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "email_address": "test@va.gov",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "something": 42,
            },
            400,
        ),
    ),
    ids=(
        "SMS with phone number",
        "e-mail with e-mail address",
        "SMS with recipient ID",
        "e-mail with recipient ID",
        "additional properties not allowed",
    )
)
def test_post_v3_notifications(notify_db_session, client, sample_service, request_data, expected_status_code):
    """
    Test e-mail and SMS POST endpoints using "email_address", "phone_number", and "recipient_identifier".
    Also test POSTing with bad request data to verify a 400 response.  This test does not exhaustively test
    request data combinations because tests/app/v3/notifications/test_notification_schemas.py handles that.

    Also test the utility function to send notifications directly (not via an API call).

    Tests for authentication are in tests/app/test_route_authentication.py.
    """

    # TODO 1361 - mock call to Celery apply_async

    auth_header = create_authorization_header(service_id=sample_service.id, key_type="team")
    response = client.post(
        path=url_for(f"v3.v3_notifications.v3_post_notification_{request_data['notification_type']}"),
        data=dumps(request_data),
        headers=(("Content-Type", "application/json"), auth_header)
    )
    assert response.status_code == expected_status_code, response.get_json()

    if expected_status_code == 202:
        assert isinstance(UUID(response.get_json().get("id")), UUID)
        assert isinstance(UUID(v3_send_notification(request_data)), UUID)
    elif expected_status_code == 400:
        assert "errors" in response.get_json()
        with pytest.raises(ValidationError):
            v3_send_notification(request_data)


@pytest.mark.parametrize(
    "request_data",
    (
        {
            "notification_type": SMS_TYPE,
            "phone_number": "This is not a phone number.",
            "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
            "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
        },
        {
            "notification_type": SMS_TYPE,
            "phone_number": "+1270123456",
            "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
            "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
        },
    ),
    ids=(
        "not a phone number",
        "not enough digits",
    )
)
def test_post_v3_notifications_phone_number_not_possible(notify_db_session, client, sample_service, request_data):
    """
    Test a phone number strings that cannot be parsed.
    """

    auth_header = create_authorization_header(service_id=sample_service.id, key_type="team")
    response = client.post(
        path=url_for(f"v3.v3_notifications.v3_post_notification_sms"),
        data=dumps(request_data),
        headers=(("Content-Type", "application/json"), auth_header)
    )
    assert response.status_code == 400

    response_json = response.get_json()
    assert response_json["errors"][0]["error"] == "BadRequest"

    # The error message varies.  The details don't matter for testing purposes.
    assert "message" in response_json["errors"][0]


def test_post_v3_notifications_phone_number_not_valid(notify_db_session, client, sample_service):
    """
    Test a possible phone number that is not valid (U.S. number for which area code doesn't exist).
    """

    request_data = {
        "notification_type": SMS_TYPE,
        "phone_number": "+1555123456",
        "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
        "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
    }

    auth_header = create_authorization_header(service_id=sample_service.id, key_type="team")
    response = client.post(
        path=url_for(f"v3.v3_notifications.v3_post_notification_sms"),
        data=dumps(request_data),
        headers=(("Content-Type", "application/json"), auth_header)
    )
    assert response.status_code == 400

    response_json = response.get_json()
    assert response_json["errors"][0]["error"] == "BadRequest"
    assert response_json["errors"][0]["message"].endswith("is not a valid phone number.")
