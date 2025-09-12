"""OAuth monitor infrastructure component.

This module manages the global OAuth callback monitor singleton.
Initialized from create_app() to avoid circular dependencies.
"""


class OAuthCallbackMonitor:
    """Monitor for OAuth callback attempts."""

    def __init__(self):
        self.attempts = {}

    def record_attempt(self, state: str) -> None:
        """Record an OAuth callback attempt."""
        self.attempts[state] = True

    def has_attempted(self, state: str) -> bool:
        """Check if an OAuth callback has been attempted."""
        return state in self.attempts


_oauth_monitor: OAuthCallbackMonitor | None = None


def init_oauth_monitor() -> None:
    """Initialize the global OAuth monitor singleton.

    This function should be called from create_app() to initialize
    the OAuth monitor singleton.
    """
    global _oauth_monitor
    if _oauth_monitor is None:
        _oauth_monitor = OAuthCallbackMonitor()


def get_oauth_monitor() -> OAuthCallbackMonitor:
    """Get the global OAuth monitor singleton.

    Returns:
        The global OAuth monitor instance

    Raises:
        RuntimeError: If the OAuth monitor has not been initialized
    """
    if _oauth_monitor is None:
        raise RuntimeError("OAuth monitor has not been initialized. Call init_oauth_monitor() first.")
    return _oauth_monitor
