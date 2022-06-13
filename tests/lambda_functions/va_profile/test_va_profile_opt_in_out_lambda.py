import os
import json
import pytest
from lambda_functions.va_profile.va_profile_opt_in_out_lambda import lambda_handler
import requests_mock

@pytest.fixture
def test_va_profile_opt_in_out_lambda(rmock):

    event = {
            "bios": [
                {
                    "txAuditId": "string",
                    "sourceDate": "2022-03-03T19:36:59.360Z",
                    "vaProfileId": 1,
                    "communicationChannelId": 2,
                    "communicationItemId": 3,
                    "allowed": true,
                }
            ]
        }

    response = lambda_handler(event)
    assert response['statusCode'] == 200