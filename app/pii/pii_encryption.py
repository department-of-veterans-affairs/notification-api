"""TODO: update docstring

Module for handling PII (Personally Identifiable Information) data.

This module provides a base class for safely handling PII data, preventing accidental
logging or exposure of sensitive information. It implements encryption for PII data
and provides controlled methods to access the actual values when needed.

Classes in this module follow guidance from:
- NIST 800-122
- NIST 800-53
- NIST 800-60
- VA Documents
"""

# Builtins
import os
from hmac import HMAC
import hashlib

# Dependencies
from cryptography.fernet import Fernet


class PiiEncryption:
    """Singleton to manage encryption for PII data."""

    _instance: 'PiiEncryption | None' = None
    _key: bytes | None = None
    _fernet: Fernet | None = None

    def __new__(cls) -> 'PiiEncryption':
        if cls._instance is None:
            cls._instance = super(PiiEncryption, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_encryption(cls) -> Fernet:
        """Get or create a Fernet instance for encryption/decryption.

        Raises:
            ValueError: If PII_ENCRYPTION_KEY environment variable is not set.
        """
        if cls._fernet is None:
            # Use environment variable - key must be provided in production
            key_str = os.getenv('PII_ENCRYPTION_KEY')
            if key_str is None:
                raise ValueError(
                    'PII_ENCRYPTION_KEY environment variable is required. '
                    'This key must be provided through AWS Parameter Store in production environments.'
                )

            # Key from SSM Parameter Store comes as string, encode to bytes
            cls._key = key_str.encode()
            cls._fernet = Fernet(cls._key)
        return cls._fernet


class PiiHMAC:
    """Manages HMAC-SHA256 deterministic hashing for PII data."""

    _key: bytes | None = None

    @classmethod
    def _get_hmac_key(cls) -> bytes:
        """Get or create an HMAC instance for deterministic hashing.

        Raises:
            ValueError: If PII_HMAC_KEY environment variable is not set.
        """
        if cls._key is None:
            # Use environment variable - key must be provided in production
            key_str = os.getenv('PII_HMAC_KEY')
            if key_str is None:
                # Fallback to use 'PII_ENCRYPTION_KEY'
                key_str = os.getenv('PII_ENCRYPTION_KEY')

                if key_str is None:
                    raise ValueError(
                        'PII_HMAC_KEY is not found. PII_ENCRYPTION_KEY env variable is required, '
                        'This key must be provided through AWS Parameter Store in production environments.'
                    )

                # Set os.env to use the same key for HMAC if PII_HMAC_KEY is not set, but PII_ENCRYPTION_KEY is set
                os.environ['PII_HMAC_KEY'] = key_str

            # Key from SSM Parameter Store comes as string, encode to bytes
            cls._key = key_str.encode()
        return cls._key

    @classmethod
    def get_hmac(cls, data: str) -> str:
        """Generates HMAC-SHA256 for the given PII data."""
        _hmac = HMAC(cls._get_hmac_key(), data.encode(), digestmod=hashlib.sha256)
        return _hmac.hexdigest()
