from app.pii.pii_base import Pii
from app.va.identifier import IdentifierType


class PiiBirlsid(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.BIRLSID


class PiiEdipi(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.EDIPI


class PiiIcn(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.ICN
