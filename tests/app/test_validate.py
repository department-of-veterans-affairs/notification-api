import pytest
from app.schema_validation import validate
from app.v2.notifications.notification_schemas import post_sms_request
from jsonschema import ValidationError


def test_validate_v2_notifications_personalisation_redaction(notify_api, mocker):
    """
    When POST data validation fails for a Notification, the request body
    should be logged with personalized information redacted.
    """
    mock_logger = mocker.patch('app.schema_validation.current_app.logger.info')

    # This is not valid POST data.
    notification_POST_request_data = {
        'personalisation': {
            'sensitive_data': "Don't reveal this!",
        },
    }

    with pytest.raises(ValidationError):
        validate(notification_POST_request_data, post_sms_request)

    # Cannot use a variable with loggers and assertions, falsely passes assertions
    mock_logger.assert_called_once_with(
        'Validation failed for: %s', {'personalisation': {'sensitive_data': '<redacted>'}}
    )


def test_validate_v2_notifications_icn_redaction(
    notify_api,
    mocker,
):
    """
    When POST data validation fails for a Notification, the request body
    should be logged with personalized information redacted.
    """
    mock_logger = mocker.patch('app.schema_validation.current_app.logger.info')
    with pytest.raises(ValidationError):
        validate({'recipient_identifier': {'id_type': 'ICN', 'id_value': '1234567890'}}, post_sms_request)

    # Cannot use a variable with loggers and assertions, falsely passes assertions
    mock_logger.assert_called_once_with(
        'Validation failed for: %s', {'recipient_identifier': {'id_type': 'ICN', 'id_value': '<redacted>'}}
    )


def test_validate_v2_notifications_icn_redaction_non_dictionary(
    notify_api,
    mocker,
):
    """
    When POST data validation fails for a Notification, the request body
    should be logged with personalized information redacted.
    """
    mock_logger = mocker.patch('app.schema_validation.current_app.logger.info')
    with pytest.raises(ValidationError):
        validate({'recipient_identifier': ['hello', 'world']}, post_sms_request)

    # Cannot use a variable with loggers and assertions, falsely passes assertions
    mock_logger.assert_called_once_with('Validation failed for: %s', {'recipient_identifier': '<redacted>'})
