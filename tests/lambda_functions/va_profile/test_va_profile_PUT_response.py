from lambda_functions.va_profile.va_profile_opt_in_out_lambda import va_profile_opt_in_out_lambda_handler
import pytest 
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def create_event(
        master_tx_audit_id: str,
        tx_audit_id: str,
        source_date: str,
        va_profile_id: int,
        communication_channel_id: int,
        communication_item_id: int,
        is_allowed: bool, jwt_value) -> dict:
    """
    Return a dictionary in the format of the payload the lambda function expects to
    receive from VA Profile via AWS API Gateway v2.
    """

    return {
        "headers": {
            "Authorization": f"Bearer {jwt_value}",
        },
        "body": {
            "txAuditId": master_tx_audit_id,
            "bios": [
                create_bios_element(
                    tx_audit_id,
                    source_date,
                    va_profile_id,
                    communication_channel_id,
                    communication_item_id, 
                    is_allowed
                )
            ],
        },
    }

def create_bios_element(
        tx_audit_id: str,
        source_date: str,
        va_profile_id: int,
        communication_channel_id: int,
        communication_item_id: int,
        is_allowed: bool) -> dict:

    return {
        "txAuditId": tx_audit_id,
        "sourceDate": source_date,
        "vaProfileId": va_profile_id,
        "communicationChannelId": communication_channel_id,
        "communicationItemId": communication_item_id,
        "allowed": is_allowed,
    }


@pytest.fixture(scope="module")
def jwt_encoded():
    # This assumes tests are run from the project root directory.
    with open("tests/lambda_functions/va_profile/key.pem", "rb") as f:
        private_key_bytes = f.read()

    private_key = serialization.load_pem_private_key(private_key_bytes, password=b"test", backend=default_backend())
    return jwt.encode({"some": "payload"}, private_key, algorithm="RS256")

@pytest.fixture
def lambda_event(jwt_encoded) -> dict:
    return {
        "headers": {
            "Authorization": f"Bearer {jwt_encoded}",
        },
        "body": {
                "txAuditId": "string",
                "sourceDate": "2022-03-07T19:37:59.320Z",
                "vaProfileId": 0,
                "communicationChannelId": 5,
                "communicationItemId": 0,
                "allowed": bool,
                 }
    }

def test_va_profile_opt_in_out_lambda_handler_PUT(mocker, lambda_event):
    """
    Test the VA Profile integration lambda by inspecting the PUT request it initiates to
    VA Profile in response to a request.
    """

    expected_put_body = create_event("tx_audit_id", "2022-04-27T16:57:16Z", 2, 3, 5, True)

    mock_HTTPS_connection_request = mocker.patch('http.client.HTTPSConnection.request')
    mock_HTTPS_connection_request.assert_called_once_with(
        "PUT",
        "/communication-hub/communication/v1/status/changelog/",
        expected_put_body,
        {"Content-Type": "application/json"}
        )

    mock_HTTPS_connection_response = mocker.patch('http.client.HTTPSConnection.response')
    mock_HTTPS_connection_response.assert_called_once()

    response = va_profile_opt_in_out_lambda_handler(expected_put_body, lambda_event, None)

    assert response['statusCode'] == 200
