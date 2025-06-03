"""Module for handling PII (Personally Identifiable Information) data.

This module provides a base class for safely handling PII data, preventing accidental
logging or exposure of sensitive information. It implements encryption for PII data
and provides controlled methods to access the actual values when needed.

Classes in this module follow guidance from:
- NIST 800-122
- NIST 800-53
- NIST 800-60
- VA Documents
"""

import os
from enum import Enum
from cryptography.fernet import Fernet


class PiiEncryption:
    """Singleton to manage encryption for PII data."""

    _instance = None
    _key = None
    _fernet = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PiiEncryption, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_fernet(cls):
        """Get or create a Fernet instance for encryption/decryption."""
        if cls._fernet is None:
            # Use environment variable or generate a new key
            # In production, this key should be managed securely
            cls._key = os.environ.get('PII_ENCRYPTION_KEY')
            if cls._key is None:
                cls._key = Fernet.generate_key()
            elif isinstance(cls._key, str):
                cls._key = cls._key.encode()

            cls._fernet = Fernet(cls._key)
        return cls._fernet


class PiiLevel(Enum):
    """Enumeration of PII impact levels based on FIPS 199 and NIST 800-122."""

    LOW = 0  # Limited adverse effect
    MODERATE = 1  # Serious adverse effect
    HIGH = 2  # Severe or catastrophic adverse effect


class Pii(str):
    """Base class for handling PII data with automatic encryption and redaction.

    This class encrypts PII data upon initialization and provides controlled access
    methods to decrypt the data when needed. It also provides string representations
    that redact the data based on its impact level.

    Attributes:
        level (PiiLevel): The impact level of the PII data, defaults to HIGH
    """

    # Default to HIGH level of impact per the ADR
    level = PiiLevel.HIGH

    # Class name is used as the suffix after "redacted" in string representations
    def __new__(cls, value: str) -> 'Pii':
        """Create a new Pii instance with encrypted value.

        Args:
            value (str): The PII value to encrypt.

        Returns:
            Pii: A new Pii instance (of a subclass) with the value encrypted.

        Raises:
            TypeError: If the `Pii` base class itself is being instantiated.
        """
        if cls is Pii:
            raise TypeError(
                'Pii base class cannot be instantiated directly. '
                'Please create a specific Pii subclass (e.g., PiiEmail, PiiSsn) '
                "and define its 'level' attribute if needed."
            )

        if value is None:
            value = ''

        # Get encryption singleton
        fernet = PiiEncryption.get_fernet()

        # Encrypt the value
        encrypted = fernet.encrypt(value.encode()).decode()

        # Return a new string instance with the encrypted value
        return super().__new__(cls, encrypted)

    def get_pii(self) -> str:
        """Decrypt and return the PII value.

        Returns:
            str: The decrypted PII value
        """
        # Get encryption singleton
        fernet = PiiEncryption.get_fernet()

        # Decrypt the value
        return fernet.decrypt(self.encode()).decode()

    def __str__(self) -> str:
        """Return a string representation with redaction based on impact level.

        For LOW impact PII, returns the encrypted value.
        For MODERATE and HIGH impact PII, returns "redacted" followed by the class name.

        Returns:
            str: String representation of the PII data
        """
        if self.level == PiiLevel.LOW:
            return super().__str__()
        else:
            # Use the class name as the suffix
            class_name = self.__class__.__name__
            return f'redacted {class_name}'

    def __repr__(self) -> str:
        """Return a string representation suitable for debugging.

        This method returns the same value as __str__ to ensure no accidental
        exposure of PII in debug logs or console output.

        Returns:
            str: Same as __str__ to avoid accidental PII exposure
        """
        return self.__str__()
