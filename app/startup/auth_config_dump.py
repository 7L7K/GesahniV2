import logging
import os

log = logging.getLogger("auth.debug")


def dump_cookie_config():
    """Log cookie-related environment configuration for debugging.

    Emitted when AUTH_DEBUG=1 to make cookie flags visible at startup.
    """
    try:
        log.info(
            "AUTH_CFG COOKIE_SECURE=%s COOKIE_SAMESITE=%s COOKIE_DOMAIN=%s COOKIE_PATH=%s ENV=%s",
            os.getenv("COOKIE_SECURE"),
            os.getenv("COOKIE_SAMESITE"),
            os.getenv("COOKIE_DOMAIN"),
            os.getenv("COOKIE_PATH") or "/",
            os.getenv("ENV"),
        )
    except Exception:
        # Do not fail startup for logging issues
        pass
