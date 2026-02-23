"""PII handling package.

This package provides classes and utilities for handling Personally Identifiable Information (PII)
in a secure manner, including encryption, redaction, and controlled access.
"""

from app.pii.pii_encryption import PiiEncryption
from app.pii.pii_base import PiiLevel, Pii
from app.pii.pii_high import PiiBirlsid, PiiEdipi, PiiIcn
from app.pii.pii_low import PiiPid, PiiVaProfileID
from app.va.identifier import IdentifierType


def get_pii_subclass(id_type: str) -> Pii:
    """
    This function intentionally does not catch KeyError.  It assumes the POST /v2/notification routes properly
    validates the POST form data.
    """

    pii_class_mapping = {
        IdentifierType.ICN.value: PiiIcn,
        IdentifierType.EDIPI.value: PiiEdipi,
        IdentifierType.BIRLSID.value: PiiBirlsid,
        IdentifierType.PID.value: PiiPid,
        IdentifierType.VA_PROFILE_ID.value: PiiVaProfileID,
    }

    return pii_class_mapping[id_type]


__all__ = [
    'Pii',
    'PiiBirlsid',
    'PiiEdipi',
    'PiiEncryption',
    'PiiIcn',
    'PiiLevel',
    'PiiPid',
    'PiiVaProfileID',
]
