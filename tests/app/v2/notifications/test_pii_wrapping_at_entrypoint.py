from unittest.mock import patch

from app.va.identifier import IdentifierType
from app.pii import PiiIcn, PiiEdipi, PiiBirlsid, PiiPid, PiiVaProfileID
from app.v2.notifications.post_notifications import wrap_recipient_identifier_in_pii


class TestPiiWrappingAtEntrypoint:
    """Tests for PII wrapping functionality at system entry point."""

    def test_wrap_recipient_identifier_feature_flag_disabled(self):
        """Test that PII wrapping is bypassed when feature flag is disabled."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=False):
            result = wrap_recipient_identifier_in_pii(form)

        # Form should be unchanged when feature flag is disabled
        assert result == form
        assert isinstance(result['recipient_identifier']['id_value'], str)
        assert result['recipient_identifier']['id_value'] == '1234567890V123456'

    def test_wrap_recipient_identifier_feature_flag_enabled_icn(self):
        """Test that ICN is wrapped in PiiIcn when feature flag is enabled."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        # id_type should remain unchanged
        assert result['recipient_identifier']['id_type'] == IdentifierType.ICN.value

        # id_value should be wrapped in PiiIcn
        assert isinstance(result['recipient_identifier']['id_value'], PiiIcn)
        assert result['recipient_identifier']['id_value'].get_pii() == '1234567890V123456'

    def test_wrap_recipient_identifier_edipi(self):
        """Test that EDIPI is wrapped in PiiEdipi."""
        form = {'recipient_identifier': {'id_type': IdentifierType.EDIPI.value, 'id_value': '1234567890'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result['recipient_identifier']['id_type'] == IdentifierType.EDIPI.value
        assert isinstance(result['recipient_identifier']['id_value'], PiiEdipi)
        assert result['recipient_identifier']['id_value'].get_pii() == '1234567890'

    def test_wrap_recipient_identifier_birlsid(self):
        """Test that BIRLSID is wrapped in PiiBirlsid."""
        form = {'recipient_identifier': {'id_type': IdentifierType.BIRLSID.value, 'id_value': 'BIRLSID123'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result['recipient_identifier']['id_type'] == IdentifierType.BIRLSID.value
        assert isinstance(result['recipient_identifier']['id_value'], PiiBirlsid)
        assert result['recipient_identifier']['id_value'].get_pii() == 'BIRLSID123'

    def test_wrap_recipient_identifier_pid(self):
        """Test that PID is wrapped in PiiPid."""
        form = {'recipient_identifier': {'id_type': IdentifierType.PID.value, 'id_value': 'PID123456'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result['recipient_identifier']['id_type'] == IdentifierType.PID.value
        assert isinstance(result['recipient_identifier']['id_value'], PiiPid)
        assert result['recipient_identifier']['id_value'].get_pii() == 'PID123456'

    def test_wrap_recipient_identifier_va_profile_id(self):
        """Test that VA_PROFILE_ID is wrapped in PiiVaProfileID."""
        form = {'recipient_identifier': {'id_type': IdentifierType.VA_PROFILE_ID.value, 'id_value': '12345'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result['recipient_identifier']['id_type'] == IdentifierType.VA_PROFILE_ID.value
        assert isinstance(result['recipient_identifier']['id_value'], PiiVaProfileID)
        assert result['recipient_identifier']['id_value'].get_pii() == '12345'

    def test_wrap_recipient_identifier_no_recipient_identifier(self):
        """Test that form without recipient_identifier is unchanged."""
        form = {'template_id': 'some-template-id', 'phone_number': '555-123-4567'}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result == form

    def test_wrap_recipient_identifier_empty_recipient_identifier(self):
        """Test that empty recipient_identifier is handled gracefully."""
        form = {'recipient_identifier': {}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result == form

    def test_wrap_recipient_identifier_missing_id_type(self):
        """Test that missing id_type is handled gracefully."""
        form = {'recipient_identifier': {'id_value': '1234567890V123456'}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result == form
        assert result['recipient_identifier']['id_value'] == '1234567890V123456'

    def test_wrap_recipient_identifier_missing_id_value(self):
        """Test that missing id_value is handled gracefully."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value}}

        with patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True):
            result = wrap_recipient_identifier_in_pii(form)

        assert result == form

    def test_wrap_recipient_identifier_unknown_id_type(self):
        """Test that unknown id_type is handled gracefully with warning log."""
        form = {'recipient_identifier': {'id_type': 'UNKNOWN_TYPE', 'id_value': 'some_value'}}

        with (
            patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True),
            patch('app.v2.notifications.post_notifications.current_app') as mock_app,
        ):
            result = wrap_recipient_identifier_in_pii(form)

        # Form should be unchanged for unknown id_type
        assert result == form
        assert result['recipient_identifier']['id_value'] == 'some_value'

        # Should log a warning
        mock_app.logger.warning.assert_called_once_with('Unknown id_type %s - cannot wrap in PII class', 'UNKNOWN_TYPE')

    def test_wrap_recipient_identifier_pii_instantiation_error(self):
        """Test that PII instantiation errors are handled gracefully."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': 'bad_value'}}

        with (
            patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True),
            patch('app.v2.notifications.post_notifications.PiiIcn', side_effect=Exception('PII error')),
            patch('app.v2.notifications.post_notifications.current_app') as mock_app,
        ):
            result = wrap_recipient_identifier_in_pii(form)

        # Form should be unchanged if PII instantiation fails
        assert result['recipient_identifier']['id_type'] == IdentifierType.ICN.value
        assert result['recipient_identifier']['id_value'] == 'bad_value'

        # Should log an error
        mock_app.logger.error.assert_called_once_with(
            'Failed to wrap recipient identifier in PII class %s: %s', 'PiiIcn', 'PII error'
        )

    def test_wrap_recipient_identifier_logging_success(self):
        """Test that successful PII wrapping is logged at debug level."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

        with (
            patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True),
            patch('app.v2.notifications.post_notifications.current_app') as mock_app,
        ):
            wrap_recipient_identifier_in_pii(form)

        # Should log success at debug level
        mock_app.logger.debug.assert_called_once_with(
            'Wrapped recipient identifier id_value in %s for id_type %s', 'PiiIcn', IdentifierType.ICN.value
        )

    def test_pii_wrapping_uses_false_for_is_encrypted_parameter(self):
        """Test that PII classes are instantiated with is_encrypted=False."""
        form = {'recipient_identifier': {'id_type': IdentifierType.ICN.value, 'id_value': '1234567890V123456'}}

        with (
            patch('app.v2.notifications.post_notifications.is_feature_enabled', return_value=True),
            patch('app.v2.notifications.post_notifications.PiiIcn') as mock_pii_icn,
        ):
            wrap_recipient_identifier_in_pii(form)

        # Verify PII class is called with is_encrypted=False
        mock_pii_icn.assert_called_once_with('1234567890V123456', False)


class TestPiiWrappingFeatureFlag:
    """Tests for the PII wrapping feature flag."""

    def test_pii_wrapping_feature_flag_is_disabled_by_default(self, mocker):
        """Test that the PII_WRAPPING_AT_ENTRYPOINT_ENABLED feature flag is disabled by default."""
        mocker.patch.dict('os.environ', {}, clear=True)
        from app.feature_flags import is_feature_enabled, FeatureFlag

        assert not is_feature_enabled(FeatureFlag.PII_WRAPPING_AT_ENTRYPOINT_ENABLED)

    def test_pii_wrapping_feature_flag_can_be_enabled(self, mocker):
        """Test that the PII_WRAPPING_AT_ENTRYPOINT_ENABLED feature flag can be enabled."""
        mocker.patch.dict('os.environ', {'PII_WRAPPING_AT_ENTRYPOINT_ENABLED': 'True'})
        from app.feature_flags import is_feature_enabled, FeatureFlag

        assert is_feature_enabled(FeatureFlag.PII_WRAPPING_AT_ENTRYPOINT_ENABLED)
