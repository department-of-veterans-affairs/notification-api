"""Module for handling PII (Personally Identifiable Information) Encryption logic.

This module provides a class for PII Fernet encryption. It implements encryption
for PII data.

Classes in this module follow guidance from:
- NIST 800-122
- NIST 800-53
- NIST 800-60
- VA Documents
"""

import os
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
