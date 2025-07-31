import os
import pytest
from unittest.mock import patch

from app.pii import PiiEncryption, PiiIcn, PiiEdipi, PiiBirlsid, PiiPid, PiiVaProfileID
from app.va.identifier import IdentifierType
from app.v2.notifications.post_notifications import wrap_recipient_identifier_in_pii

# Constant test key for consistent encryption/decryption during tests
# Using a fixed test key - this is only for testing and not a real secret
# The value is the base64 encoding of "This is an 32 byte key for tests"
TEST_KEY = b'VGhpcyBpcyBhbiAzMiBieXRlIGtleSBmb3IgdGVzdHM='


@pytest.fixture(autouse=True)
def setup_encryption():
    """Setup encryption with a consistent key for tests.

    This fixture resets the PiiEncryption singleton to use a test key
    for consistent encryption/decryption during tests.
    """
    with (
        patch.object(PiiEncryption, '_key', None),
        patch.object(PiiEncryption, '_fernet', None),
        patch.dict(os.environ, {'PII_ENCRYPTION_KEY': TEST_KEY.decode()}),
    ):
        yield


class TestPiiWrappingAtEntrypoint:
    """Tests for PII wrapping functionality at system entry point."""

    @pytest.mark.parametrize(
        'id_type,id_value,expected_pii_class',
        [
            (IdentifierType.ICN.value, '1234567890V123456', PiiIcn),
            (IdentifierType.EDIPI.value, '1234567890', PiiEdipi),
            (IdentifierType.BIRLSID.value, 'BIRLSID123', PiiBirlsid),
            (IdentifierType.PID.value, 'PID123456', PiiPid),
            (IdentifierType.VA_PROFILE_ID.value, '12345', PiiVaProfileID),
        ],
    )
    def test_wrap_recipient_identifier_all_types(self, notify_api, id_type, id_value, expected_pii_class):
        """Test that all identifier types are wrapped in their corresponding PII classes."""
        with notify_api.app_context():
            form = {'recipient_identifier': {'id_type': id_type, 'id_value': id_value}}

            result = wrap_recipient_identifier_in_pii(form)

            # id_type should remain unchanged
            assert result['recipient_identifier']['id_type'] == id_type
            # id_value should be wrapped in the expected PII class
            assert isinstance(result['recipient_identifier']['id_value'], expected_pii_class)
            assert result['recipient_identifier']['id_value'].get_pii() == id_value

    @pytest.mark.parametrize(
        'form,description',
        [
            ({'template_id': 'some-template-id', 'phone_number': '555-123-4567'}, 'no recipient_identifier'),
            ({'recipient_identifier': {}}, 'empty recipient_identifier'),
            ({'recipient_identifier': {'id_value': '1234567890V123456'}}, 'missing id_type'),
            ({'recipient_identifier': {'id_type': IdentifierType.ICN.value}}, 'missing id_value'),
        ],
    )
    def test_wrap_recipient_identifier_edge_cases(self, notify_api, form, description):
        """Test that edge cases are handled gracefully."""
        with notify_api.app_context():
            original_form = form.copy()
            result = wrap_recipient_identifier_in_pii(form)

            # Form should be unchanged for all edge cases
            assert result == original_form

    def test_wrap_recipient_identifier_unknown_id_type(self, notify_api):
        """Test that unknown id_type is handled gracefully with warning log."""
        with notify_api.app_context():
            form = {'recipient_identifier': {'id_type': 'UNKNOWN_TYPE', 'id_value': 'some_value'}}

            result = wrap_recipient_identifier_in_pii(form)

            # Form should be unchanged for unknown id_type
            assert result == form
            assert result['recipient_identifier']['id_value'] == 'some_value'

    def test_wrap_recipient_identifier_logging_success(self, notify_api):
        """Test that successful PII wrapping works correctly."""
        with notify_api.app_context():
            form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

            result = wrap_recipient_identifier_in_pii(form)

            # Verify the PII object was created successfully
            assert isinstance(result['recipient_identifier']['id_value'], PiiIcn)
            assert result['recipient_identifier']['id_value'].get_pii() == '1234567890V123456'

    def test_wrap_recipient_identifier_pii_instantiation_error(self, notify_api):
        """Test that PII instantiation errors are handled gracefully."""
        with notify_api.app_context():
            form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': 'bad_value'}}

            with patch(
                'app.v2.notifications.post_notifications.PiiIcn', side_effect=Exception('PII error')
            ) as mock_pii_icn:
                mock_pii_icn.__name__ = 'PiiIcn'
                result = wrap_recipient_identifier_in_pii(form)

            # Form should be unchanged if PII instantiation fails
            assert result['recipient_identifier']['id_type'] == IdentifierType.ICN.value
            assert result['recipient_identifier']['id_value'] == 'bad_value'

    def test_pii_wrapping_uses_false_for_is_encrypted_parameter(self, notify_api):
        """Test that PII classes are instantiated with is_encrypted=False."""
        with notify_api.app_context():
            form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

            with patch('app.v2.notifications.post_notifications.PiiIcn') as mock_pii_icn:
                mock_pii_icn.__name__ = 'PiiIcn'
                wrap_recipient_identifier_in_pii(form)

            # Verify PII class was called with is_encrypted=False
            mock_pii_icn.assert_called_once_with('1234567890V123456', False)


class TestPiiWrappingFeatureFlag:
    """Tests for the PII wrapping feature flag."""

    @pytest.mark.parametrize(
        'env_value,expected',
        [
            ({}, False),  # disabled by default
            ({'PII_ENABLED': 'True'}, True),  # can be enabled
            ({'PII_ENABLED': 'False'}, False),  # can be explicitly disabled
        ],
    )
    def test_pii_enabled_feature_flag(self, mocker, env_value, expected):
        """Test PII_ENABLED feature flag behavior."""
        mocker.patch.dict('os.environ', env_value, clear=True)
        from app.feature_flags import is_feature_enabled, FeatureFlag

        assert is_feature_enabled(FeatureFlag.PII_ENABLED) == expected
