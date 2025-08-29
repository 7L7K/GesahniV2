from __future__ import annotations

import os


def bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def get_lazy_refresh_window_s() -> int:
    # Explicit override wins
    if os.getenv("AUTH_LAZY_REFRESH_WINDOW_S"):
        try:
            return max(1, int(os.getenv("AUTH_LAZY_REFRESH_WINDOW_S", "60")))
        except Exception:
            return 60
    # Default: 60 in dev, 90 in prod-ish (COOKIE_SECURE or ENV=prod)
    is_prod = bool_env("COOKIE_SECURE") or os.getenv("ENV", "").lower() in {"prod", "production"}
    return 90 if is_prod else 60


__all__ = ["get_lazy_refresh_window_s", "bool_env"]

