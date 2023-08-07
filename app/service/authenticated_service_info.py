import json
from types import SimpleNamespace


class AuthenticatedServiceInfoException(Exception):
    def __init__(self, message="A custom exception occurred", *args, **kwargs):
        super().__init__(message, *args, **kwargs)


class AuthenticatedServiceApiKey:
    def __init__(self, key) -> None:
        self.created_at = key.created_at
        self.created_by = key.created_by
        self.created_by_id = key.created_by_id
        self.expiry_date = key.expiry_date
        self.id = key.id
        self.key_type = key.key_type
        self.name = key.name
        self.secret = key.secret
        # this is another example of circular dependency
        # and multilevel nesting. Creating simple namespance
        # to preseve dot notation used in calling functions.
        _service = {
            "research_mode": key.service.research_mode,
            "restricted": key.service.restricted,
            "active": key.service.active,
        }
        self.service = SimpleNamespace(**_service)
        self.service_id = key.service_id
        self.updated_at = key.updated_at


class AuthenticatedServiceInfo:
    def __init__(self, result=None):
        self.active = None
        self.permissions = None
        self.api_keys = None
        self.id = None
        self.research_mode = None
        self.restricted = None
        self.rate_limit = None
        self.service_sms_senders = None
        self.message_limit = None
        self.users = None
        self.whitelist = None
        if result is not None:
            try:
                self.extract(result)
            except Exception as err:
                raise AuthenticatedServiceInfoException(err)

    # method to extract the nessessary data from authenticated service orm object
    def extract(self, result):
        self.active = result.active
        self.permissions = [p.permission for p in result.permissions]
        self.api_keys = [AuthenticatedServiceApiKey(key) for key in result.api_keys]
        self.id = result.id
        self.research_mode = result.research_mode
        self.restricted = result.restricted
        self.rate_limit = result.rate_limit
        self.service_sms_senders = result.service_sms_senders
        self.message_limit = result.message_limit
        self.users = [u for u in result.users]
        self.whitelist = [w for w in result.whitelist]

    # method might be used for caching
    def serialize(self):
        return json.dumps(self.__dict__)

    def has_permissions(self, permissions_to_check_for):
        if type(permissions_to_check_for) is not list:
            tmp = permissions_to_check_for
            permissions_to_check_for = [tmp]
        return set(permissions_to_check_for).issubset(set(self.permissions))

    # method creates a new instance of class
    # and might be used after retrival from caching
    @classmethod
    def deserialize(cls, json_string):
        result = cls()
        result.__dict__ = json.loads(json_string)
        return result
