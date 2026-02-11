class RetryableException(Exception):
    def __init__(self, message='', *, use_non_priority_handling=False):
        super().__init__(message)
        self.use_non_priority_handling = use_non_priority_handling


class NonRetryableException(Exception):
    pass


class AutoRetryException(Exception):
    pass
