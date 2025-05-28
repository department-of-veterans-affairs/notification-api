"""Tests for the get_secret_generator helper function."""

from uuid import UUID

from app.service.rest import get_secret_generator


def test_get_secret_generator_with_uuid_returns_uuid_generator():
    """Test that requesting 'uuid' secret type returns a function that generates UUIDs."""
    generator = get_secret_generator('uuid')

    assert generator is not None
    assert callable(generator)

    # Test that the generator produces valid UUID strings
    secret = generator()
    assert isinstance(secret, str)
    assert len(secret) == 36  # Standard UUID string length

    # Verify it's a valid UUID by parsing it
    parsed_uuid = UUID(secret)
    assert str(parsed_uuid) == secret


def test_get_secret_generator_with_none_returns_none():
    """Test that requesting None secret type returns None."""
    generator = get_secret_generator(None)
    assert generator is None


def test_get_secret_generator_with_empty_string_returns_none():
    """Test that requesting empty string secret type returns None."""
    generator = get_secret_generator('')
    assert generator is None


def test_get_secret_generator_with_unknown_type_returns_none():
    """Test that requesting unknown secret type returns None."""
    generator = get_secret_generator('unknown_type')
    assert generator is None


def test_get_secret_generator_uuid_produces_unique_values():
    """Test that the UUID generator produces unique values on each call."""
    generator = get_secret_generator('uuid')

    # Generate multiple UUIDs and ensure they're all different
    secrets = [generator() for _ in range(10)]
    assert len(set(secrets)) == 10  # All should be unique

    # Verify all are valid UUIDs
    for secret in secrets:
        UUID(secret)  # This will raise ValueError if invalid
