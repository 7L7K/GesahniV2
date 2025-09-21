from __future__ import annotations

import warnings
from typing import Any

from fastapi import APIRouter

# DEPRECATED: Import from app.auth.endpoints.* instead
warnings.warn(
    "DEPRECATED: app.api.auth is deprecated. Import from app.auth.endpoints.* instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Create router instance for compatibility
router = APIRouter()


class _DeprecatedAccess:
    """Wrapper to warn when deprecated exports are accessed."""

    def __init__(self, obj, name: str, message: str):
        self._obj = obj
        self._name = name
        self._message = message
        self._warned = False

    def __call__(self, *args, **kwargs):
        if not self._warned:
            warnings.warn(self._message, DeprecationWarning, stacklevel=2)
            self._warned = True
        return self._obj(*args, **kwargs)

    def __getattr__(self, name):
        if not self._warned:
            warnings.warn(self._message, DeprecationWarning, stacklevel=2)
            self._warned = True
        return getattr(self._obj, name)


# Import canonical endpoints for re-export
from app.auth.endpoints import debug as _dbg  # noqa: E402
from app.auth.endpoints import login as _login  # noqa: E402
from app.auth.endpoints import logout as _logout  # noqa: E402
from app.auth.endpoints import refresh as _refresh  # noqa: E402
from app.auth.endpoints import register as _register  # noqa: E402
from app.auth.endpoints import token as _token  # noqa: E402

# Re-export canonicals with deprecation warnings
debug_cookies = _DeprecatedAccess(
    _dbg.debug_cookies, "debug_cookies", "DEPRECATED: import from app.auth.endpoints.debug"
)
debug_auth_state = _DeprecatedAccess(
    _dbg.debug_auth_state, "debug_auth_state", "DEPRECATED: import from app.auth.endpoints.debug"
)
whoami = _DeprecatedAccess(_dbg.whoami, "whoami", "DEPRECATED: import from app.auth.endpoints.debug")

login = _DeprecatedAccess(_login.login, "login", "DEPRECATED: import from app.auth.endpoints.login")
login_v1 = _DeprecatedAccess(_login.login_v1, "login_v1", "DEPRECATED: import from app.auth.endpoints.login")

logout = _DeprecatedAccess(_logout.logout, "logout", "DEPRECATED: import from app.auth.endpoints.logout")
logout_all = _DeprecatedAccess(
    _logout.logout_all, "logout_all", "DEPRECATED: import from app.auth.endpoints.logout"
)

refresh = _DeprecatedAccess(_refresh.refresh, "refresh", "DEPRECATED: import from app.auth.endpoints.refresh")

register_v1 = _DeprecatedAccess(
    _register.register_v1, "register_v1", "DEPRECATED: import from app.auth.endpoints.register"
)

dev_token = _DeprecatedAccess(_token.dev_token, "dev_token", "DEPRECATED: import from app.auth.endpoints.token")
token_examples = _DeprecatedAccess(
    _token.token_examples, "token_examples", "DEPRECATED: import from app.auth.endpoints.token"
)

# Keep rotate shim as a plain forward (tests may import it)
rotate_refresh_cookies = _refresh.rotate_refresh_cookies

__all__ = [
    "debug_cookies",
    "debug_auth_state", 
    "whoami",
    "login",
    "login_v1",
    "logout",
    "logout_all",
    "refresh",
    "register_v1",
    "dev_token",
    "token_examples",
    "rotate_refresh_cookies",
    "router",
]
