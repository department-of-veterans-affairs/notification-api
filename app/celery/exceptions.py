class RetryableException(Exception):
    """
    Indicates a transient failure that should be retried.

    The ``use_non_priority_handling`` flag signals that retry handling should
    override the default behavior (e.g., route to a non-priority queue).
    """

    def __init__(
        self,
        message: str = '',
        *,
        use_non_priority_handling: bool = False,
    ) -> None:
        super().__init__(message)
        self.use_non_priority_handling = use_non_priority_handling


class NonRetryableException(Exception):
    pass


class AutoRetryException(Exception):
    pass
