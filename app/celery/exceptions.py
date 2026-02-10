class RetryableException(Exception):
    pass


class RetryableException_NonPriority(RetryableException):
    pass


class NonRetryableException(Exception):
    pass


class AutoRetryException(Exception):
    pass
