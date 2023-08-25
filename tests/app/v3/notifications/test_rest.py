""" Test endpoints for the v3 notifications. """

import pytest
from app.models import EMAIL_TYPE, SMS_TYPE
from flask import url_for
from json import dumps
from tests import create_authorization_header
from uuid import UUID


@pytest.mark.parametrize(
    "request_data, expected_status_code",
    (
        (
            {
                "notification_type": SMS_TYPE,
                "to": "+12701234567",
                "sms_sender_id": "4f365dd4-332e-454d-94ff-e393463602db",
                "template_id": "4f365dd4-332e-454d-94ff-e393463602db",
            },
            202,
        ),
        (
            {
                "notification_type": EMAIL_TYPE,
                "to": "test@va.gov",
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
                "to": "test@va.gov",
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
def test_post_notification_v3(notify_db_session, client, sample_service, request_data, expected_status_code):
    """
    Test e-mail and SMS POST endpoints using "to" and "recipient_identifier".  Also test POSTing
    with bad request data to verify a 400 response.  This test does not exhaustively test
    request data combinations because tests/app/v3/notifications/test_notification_schemas.py
    handles that.

    Tests for authentication are in tests/app/test_route_authentication.py.
    """

    # TODO 1361 - mock call to Celery apply_async

    auth_header = create_authorization_header(service_id=sample_service.id, key_type="team")
    response = client.post(
        path=url_for(f"v3.v3_notifications.v3_notification_{request_data['notification_type']}"),
        data=dumps(request_data),
        headers=(("Content-Type", "application/json"), auth_header)
    )
    assert response.status_code == expected_status_code

    if expected_status_code == 202:
        assert isinstance(UUID(response.get_json().get("id")), UUID)
    elif expected_status_code == 400:
        assert "errors" in response.get_json()
