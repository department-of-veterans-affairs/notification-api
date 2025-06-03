import os
import pytest
from unittest.mock import patch

from app.pii import PiiEncryption, PiiLevel, Pii


@pytest.fixture
def test_key():
    """Fixture to provide a consistent encryption key for tests."""
    # Using a fixed test key - this is only for testing and not a real secret
    # The value is the base64 encoding of "This is an 32 byte key for tests"
    return b'VGhpcyBpcyBhbiAzMiBieXRlIGtleSBmb3IgdGVzdHM='


@pytest.fixture
def setup_encryption(test_key):
    """Setup encryption with a consistent key for tests.

    This fixture resets the PiiEncryption singleton to use a test key
    for consistent encryption/decryption during tests.
    """
    with patch.object(PiiEncryption, '_key', test_key), patch.object(PiiEncryption, '_fernet', None):
        yield


class TestPiiEncryption:
    """Tests for the PiiEncryption class."""

    def test_singleton_pattern(self):
        """Test that PiiEncryption follows the singleton pattern."""
        encryption1 = PiiEncryption()
        encryption2 = PiiEncryption()
        assert encryption1 is encryption2

    def test_get_encryption_generates_key_if_not_exists(self, setup_encryption):
        """Test that get_encryption generates a key if one doesn't exist."""
        # Reset the key to None for this test
        with patch.object(PiiEncryption, '_key', None):
            with patch.dict(os.environ, {}, clear=True):
                pii_encryption = PiiEncryption.get_encryption()
                assert pii_encryption is not None
                assert PiiEncryption._key is not None

    def test_get_encryption_uses_environment_variable(self, test_key):
        """Test that get_encryption uses the environment variable if available."""
        with patch.object(PiiEncryption, '_fernet', None):
            with patch.object(PiiEncryption, '_key', None):
                with patch.dict(os.environ, {'PII_ENCRYPTION_KEY': test_key.decode()}):
                    pii_encryption = PiiEncryption.get_encryption()
                    assert pii_encryption is not None
                    assert PiiEncryption._key == test_key

    def test_get_encryption_caches_fernet_instance(self, setup_encryption):
        """Test that get_encryption caches the Fernet instance."""
        pii_encryption1 = PiiEncryption.get_encryption()
        pii_encryption2 = PiiEncryption.get_encryption()
        assert pii_encryption1 is pii_encryption2


class TestPiiLevel:
    """Tests for the PiiLevel enumeration."""

    def test_pii_level_values(self):
        """Test that PiiLevel has the correct values."""
        assert PiiLevel.LOW.value == 0
        assert PiiLevel.MODERATE.value == 1
        assert PiiLevel.HIGH.value == 2

    def test_pii_level_ordering(self):
        """Test that PiiLevel values are ordered correctly."""
        assert PiiLevel.LOW.value < PiiLevel.MODERATE.value
        assert PiiLevel.MODERATE.value < PiiLevel.HIGH.value
        assert PiiLevel.LOW.value < PiiLevel.HIGH.value


class TestPii:
    """Tests for the Pii base class."""

    def test_base_class_cannot_be_instantiated(self):
        """Test that the Pii base class cannot be instantiated directly."""
        with pytest.raises(TypeError, match='Pii base class cannot be instantiated directly'):
            Pii('should_fail')

    # Helper subclass for testing the Pii base class functionality
    class PiiTest(Pii):
        """Test subclass of Pii to test base functionality."""

        _level = PiiLevel.HIGH  # Default to HIGH

    def test_initialization_encrypts_value(self, setup_encryption):
        """Test that initializing a Pii subclass encrypts the value."""
        pii = self.PiiTest('test_value')
        assert isinstance(pii, str)
        assert pii != 'test_value'  # Value should be encrypted

    def test_get_pii_decrypts_value(self, setup_encryption):
        """Test that get_pii decrypts the value correctly."""
        pii = self.PiiTest('test_value')
        assert pii.get_pii() == 'test_value'

    def test_str_representation_high_impact(self):
        """Test that string representation is redacted for HIGH impact PII."""

        # Create a temporary subclass with HIGH level
        class PiiHighTest(Pii):
            _level = PiiLevel.HIGH

        pii = PiiHighTest('test_value')
        assert str(pii) == 'redacted PiiHighTest'

    def test_str_representation_moderate_impact(self):
        """Test that string representation is redacted for MODERATE impact PII."""

        # Create a temporary subclass with MODERATE level
        class PiiModerateTest(Pii):
            _level = PiiLevel.MODERATE

        pii = PiiModerateTest('test_value')
        assert str(pii) == 'redacted PiiModerateTest'

    def test_str_representation_low_impact(self, setup_encryption):
        """Test that string representation shows encrypted value for LOW impact PII."""

        # Create a temporary subclass with LOW level
        class PiiLowTest(Pii):
            _level = PiiLevel.LOW

        pii = PiiLowTest('test_value')
        encrypted_value = str(pii)
        assert encrypted_value != 'test_value'  # Should be encrypted
        assert 'redacted' not in encrypted_value

    def test_repr_matches_str(self):
        """Test that repr() matches str() to prevent accidental exposure."""
        # Use our defined test subclass
        pii = self.PiiTest('test_value')
        assert repr(pii) == str(pii)

    def test_class_name_in_string_representation(self):
        """Test that class name appears in string representation."""
        # Use our defined test subclass which defaults to HIGH
        pii = self.PiiTest('test_value')
        assert str(pii) == 'redacted PiiTest'

    def test_none_value_handled(self):
        """Test that None value is handled safely."""

        class PiiClassForNone(Pii):
            _level = PiiLevel.LOW

        pii = PiiClassForNone(None)  # type: ignore
        assert pii.get_pii() == ''


# New test class for PII subclassing
class TestPiiSubclassing:
    """Tests for Pii subclassing behavior."""

    class PiiFirstName(Pii):
        _level: PiiLevel = PiiLevel.LOW  # Should not appear since it will log the encrypted value

    class PiiVaProileId(Pii):
        _level: PiiLevel = PiiLevel.MODERATE

    class PiiIcn(Pii):
        # The VA has said ICNs are PII - defaults to HIGH level
        pass

    # Use the module-level setup_encryption fixture with autouse
    @pytest.fixture(autouse=True)
    def use_setup_encryption(self, setup_encryption):
        """Use the module-level setup_encryption fixture for all tests in this class."""
        # The fixture yields automatically because we're using the module-level fixture
        pass

    def test_firstname_low_level_behavior(self):
        """Test that PiiFirstName (LOW level) shows encrypted value and decrypts correctly."""
        first_name = self.PiiFirstName('John')
        # For LOW level, str() should show the encrypted value, not 'redacted'
        encrypted_value = str(first_name)
        assert encrypted_value != 'John'  # Should be encrypted
        assert 'redacted' not in encrypted_value  # Should not be redacted for LOW level
        # get_pii() should decrypt correctly
        assert first_name.get_pii() == 'John'
        assert self.PiiFirstName._level == PiiLevel.LOW

    def test_va_profile_id_moderate_level_behavior(self):
        """Test that PiiVaProileId (MODERATE level) shows redacted value and decrypts correctly."""
        profile_id = self.PiiVaProileId('12345')
        # For MODERATE level, str() should show 'redacted' with class name
        assert str(profile_id) == 'redacted PiiVaProileId'
        # get_pii() should decrypt correctly
        assert profile_id.get_pii() == '12345'
        assert self.PiiVaProileId._level == PiiLevel.MODERATE

    def test_icn_high_level_behavior(self):
        """Test that PiiIcn (HIGH level by default) shows redacted value and decrypts correctly."""
        icn = self.PiiIcn('67890')
        # For HIGH level, str() should show 'redacted' with class name
        assert str(icn) == 'redacted PiiIcn'
        # get_pii() should decrypt correctly
        assert icn.get_pii() == '67890'
        # Verify the default level is HIGH
        assert icn.level == PiiLevel.HIGH
        assert self.PiiIcn._level == PiiLevel.HIGH

    def test_subclass_handles_none_value(self):
        """Test that subclasses handle None value correctly."""
        # Use None as a string value to pass type checking but test None handling in __new__
        first_name = self.PiiFirstName(None)  # type: ignore
        profile_id = self.PiiVaProileId(None)  # type: ignore
        icn = self.PiiIcn(None)  # type: ignore

        # All should return empty string when decrypting None
        assert first_name.get_pii() == ''
        assert profile_id.get_pii() == ''
        assert icn.get_pii() == ''

        # LOW level should still show encrypted value (of empty string)
        assert 'redacted' not in str(first_name)
        # MODERATE and HIGH should show redacted
        assert str(profile_id) == 'redacted PiiVaProileId'
        assert str(icn) == 'redacted PiiIcn'

    def test_repr_matches_str_in_subclasses(self):
        """Test that repr() matches str() in subclasses to prevent accidental exposure."""
        first_name = self.PiiFirstName('John')
        profile_id = self.PiiVaProileId('12345')
        icn = self.PiiIcn('67890')

        assert repr(first_name) == str(first_name)
        assert repr(profile_id) == str(profile_id)
        assert repr(icn) == str(icn)
