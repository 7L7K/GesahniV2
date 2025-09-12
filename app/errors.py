'''Application-level errors for routers and backends.'''


class BackendUnavailableError(RuntimeError):
    """Raised when a configured backend cannot be resolved at startup."""

    def __init__(self, message: str):
        super().__init__(message)


