import json

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
        if result is not None:
            self.extract(result)

    # method to extract the nessessary data from authenticated service orm object
    def extract(self, result):
        self.active = result.active
        self.permissions = [p.permission for p in result.permissions]
        self.api_keys = [k for k in result.api_keys]
        self.id = result.id
        self.research_mode = result.research_mode
        self.restricted = result.restricted
        self.rate_limit = result.rate_limit
        self.service_sms_senders = result.service_sms_senders
        self.message_limit = result.message_limit

    # method might be used for caching
    def serialize(self):
        return json.dumps(self.__dict__)

    # method creates a new instance of class
    # and might be used after retrival from caching
    @classmethod
    def deserialize(cls, json_string):
        result = cls()
        result.__dict__ = json.loads(json_string)
        return result
