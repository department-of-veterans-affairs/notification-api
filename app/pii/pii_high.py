from app.pii.pii_base import Pii
from app.va.identifier import IdentifierType


class PiiBurlsid(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.BURLSID


class PiiEdipi(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.EDIPI


class PiiIcn(Pii):
    def get_identifier_type(self) -> IdentifierType:
        return IndentifierType.ICN
