from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Sequence
from fastapi import FastAPI

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouterSpec:
    import_path: str
    prefix: str = ""
    include_in_schema: bool = True


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_router(path: str):
    mod, attr = path.split(":", 1)
    m = __import__(mod, fromlist=[attr])
    return getattr(m, attr)


def _must(specs: Sequence[RouterSpec]) -> list[RouterSpec]:
    return list(specs)


def _optional(enabled: bool, specs: Sequence[RouterSpec]) -> list[RouterSpec]:
    return list(specs) if enabled else []


def _env_name() -> str:
    return (os.getenv("ENV") or "dev").strip().lower()


def build_plan() -> list[RouterSpec]:
    env = _env_name()
    in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ

    core = _must([
        RouterSpec("app.router.ask_api:router", "/v1"),
        RouterSpec("app.router.auth_api:router", "/v1/auth"),
        RouterSpec("app.router.google_api:router", "/v1/google"),
        RouterSpec("app.router.admin_api:router", "/v1/admin"),
        RouterSpec("app.api.config_check:router", ""),  # Config check endpoint
        RouterSpec("app.router.compat_api:router", ""),  # Deprecated compatibility routes
        RouterSpec("app.api.health:router", ""),
        RouterSpec("app.api.root:router", ""),
        RouterSpec("app.status:router", "/v1"),
        RouterSpec("app.api.schema:router", ""),
        RouterSpec("app.api.google_oauth:router", "/v1/google"),
        RouterSpec("app.api.google_compat:router", ""),  # Deprecated Google OAuth compatibility
        RouterSpec("app.api.google:integrations_router", "/v1"),
        RouterSpec("app.auth:router", "/v1"),
    ])

    enable_spotify = _is_truthy(os.getenv("SPOTIFY_ENABLED")) and not in_ci
    enable_apple = _is_truthy(os.getenv("APPLE_OAUTH_ENABLED")) and not in_ci
    enable_device = _is_truthy(os.getenv("DEVICE_AUTH_ENABLED")) and not in_ci
    enable_preflt = _is_truthy(os.getenv("PREFLIGHT_ENABLED", "1"))

    optional: list[RouterSpec] = []
    optional += _optional(enable_spotify, [
        RouterSpec("app.api.spotify:integrations_router", "/v1"),
        RouterSpec("app.api.spotify:integrations_router", "/v1/integrations/spotify"),
    ])
    optional += _optional(enable_apple, [RouterSpec("app.api.oauth_apple:router", "/v1")])
    optional += _optional(enable_device, [RouterSpec("app.auth_device:router", "/v1")])
    optional += _optional(enable_preflt, [RouterSpec("app.api.preflight:router", "/v1")])

    plan = core + optional
    log.info("router.plan env=%s ci=%s total=%d (spotify=%s apple=%s device=%s preflight=%s)",
             env, in_ci, len(plan), enable_spotify, enable_apple, enable_device, enable_preflt)
    return plan


def register_routers(app: FastAPI) -> None:
    for spec in build_plan():
        try:
            r = _load_router(spec.import_path)
            app.include_router(r, prefix=spec.prefix, include_in_schema=spec.include_in_schema)
        except Exception as e:
            log.warning("router include failed: %s (%s)", spec.import_path, e)
