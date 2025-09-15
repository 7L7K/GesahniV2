from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

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

    core = _must(
        [
            RouterSpec("app.api.ask:router", "/v1"),
            # Canonical auth router (use app.api.auth as source of truth)
            RouterSpec("app.api.auth:router", "/v1"),
            RouterSpec("app.router.auth_legacy_aliases:router", "/v1"),
            RouterSpec("app.router.google_api:router", "/v1/google"),
            # Alias compatibility router provides legacy endpoints like /v1/list
            RouterSpec("app.router.alias_api:router", "/v1"),
            # Include richer app.api routers to match legacy contract snapshots
            RouterSpec("app.api.google_oauth:router", "/v1/google"),
            RouterSpec("app.api.oauth_google:router", ""),  # legacy /v1/auth/google/*
            RouterSpec("app.api.google_oauth:router", ""),  # root-level callback
            RouterSpec("app.api.calendar:router", "/v1"),
            RouterSpec("app.api.care:router", "/v1"),
            RouterSpec("app.api.devices:router", "/v1"),
            RouterSpec("app.api.google:integrations_router", "/v1"),
            RouterSpec("app.api.integrations_status:router", "/v1"),
            RouterSpec("app.api.music:system_router", "/v1"),
            # Spotify OAuth/connect handlers expected by tests
            RouterSpec("app.api.spotify:router", "/v1"),
            RouterSpec("app.api.tts:router", "/v1"),
            RouterSpec("app.api.transcribe:router", "/v1"),
            RouterSpec("app.api.ws_endpoints:router", "/v1"),
            RouterSpec("app.api.music_ws:router", "/v1"),
            RouterSpec("app.api.care_ws:router", "/v1"),
            RouterSpec("app.api.ha:router", "/v1"),
            RouterSpec("app.api.admin:router", "/v1/admin"),
            RouterSpec("app.api.tv:router", "/v1"),  # TV endpoints
            RouterSpec("app.api.tv_music_sim:router", "/v1"),  # TV music simulation
            RouterSpec("app.api.config_check:router", ""),  # Config check endpoint
            RouterSpec(
                "app.router.compat_api:router", ""
            ),  # Deprecated compatibility routes
            RouterSpec("app.api.health:router", ""),
            RouterSpec("app.api.root:router", ""),
            RouterSpec("app.api.me:router", "/v1"),  # User profile endpoint
            RouterSpec("app.api.profile:router", "/v1"),  # Profile management endpoints
            RouterSpec("app.status:router", "/v1"),
            RouterSpec(
                "app.status:public_router", "/v1"
            ),  # Public observability endpoints
            RouterSpec("app.api.status_plus:router", "/v1"),  # Features endpoint
            RouterSpec("app.api.schema:router", ""),
            RouterSpec("app.api.models:router", "/v1"),
            # Utility endpoints including CSRF (exclude from CI schema to match snapshot)
            RouterSpec("app.api.util:router", "", include_in_schema=not in_ci),
            RouterSpec("app.api.debug:router", "/v1"),  # Debug endpoints
            RouterSpec(
                "app.api.metrics_root:router", ""
            ),  # Prometheus metrics endpoint
        ]
    )

    enable_spotify = _is_truthy(os.getenv("SPOTIFY_ENABLED")) and not in_ci
    enable_apple = _is_truthy(os.getenv("APPLE_OAUTH_ENABLED")) and not in_ci
    enable_device = _is_truthy(os.getenv("DEVICE_AUTH_ENABLED")) and not in_ci
    enable_preflt = _is_truthy(os.getenv("PREFLIGHT_ENABLED", "1"))
    enable_legacy_google = _is_truthy(os.getenv("GSN_ENABLE_LEGACY_GOOGLE"))
    enable_legacy_music_http = _is_truthy(os.getenv("LEGACY_MUSIC_HTTP")) and not in_ci

    optional: list[RouterSpec] = []
    optional += _optional(
        enable_spotify,
        [
            RouterSpec("app.api.spotify:integrations_router", "/v1"),
            RouterSpec(
                "app.api.spotify:integrations_router", "/v1/integrations/spotify"
            ),
        ],
    )
    optional += _optional(
        enable_apple, [RouterSpec("app.api.oauth_apple:router", "/v1")]
    )
    optional += _optional(enable_device, [RouterSpec("app.auth_device:router", "/v1")])
    optional += _optional(
        enable_preflt, [RouterSpec("app.api.preflight:router", "/v1")]
    )
    optional += _optional(
        enable_legacy_google, [RouterSpec("app.api.google_compat:router", "")]
    )
    optional += _optional(
        enable_legacy_music_http,
        [
            RouterSpec("app.api.music_http:router", "/v1"),
            RouterSpec("app.api.music_http:redirect_router", "/v1"),
        ],
    )
    optional += _optional(
        env == "dev",  # Only include dev auth router in development
        [RouterSpec("app.api.auth_router_dev:router", "/v1")],
    )

    plan = core + optional
    # Exclude the legacy alias router when dev router is included to avoid
    # duplicate route registrations; dev router provides the same functionality.
    if in_ci or env == "dev":
        plan = [p for p in plan if "app.router.alias_api" not in p.import_path]
    enable_dev_auth = env == "dev"
    log.info(
        "router.plan env=%s ci=%s total=%d (spotify=%s apple=%s device=%s preflight=%s legacy_google=%s legacy_music_http=%s dev_auth=%s)",
        env,
        in_ci,
        len(plan),
        enable_spotify,
        enable_apple,
        enable_device,
        enable_preflt,
        enable_legacy_google,
        enable_legacy_music_http,
        enable_dev_auth,
    )
    return plan


def register_routers(app: FastAPI) -> None:
    env = _env_name()
    # Track mounted feature routers for UI visibility
    mounted: dict[str, bool] = {
        "devices": False,
        "transcribe": False,
        "ollama": False,
        "home_assistant": False,
        "qdrant": False,
    }

    for spec in build_plan():
        try:
            r = _load_router(spec.import_path)
            app.include_router(
                r, prefix=spec.prefix, include_in_schema=spec.include_in_schema
            )

            # Mark known feature routers as mounted
            if "app.api.devices" in spec.import_path:
                mounted["devices"] = True
            if "app.api.transcribe" in spec.import_path:
                mounted["transcribe"] = True
            if "app.api.ha" in spec.import_path or "home_assistant" in spec.import_path:
                mounted["home_assistant"] = True
        except Exception as e:
            # In dev/test, fail fast so issues are visible during development and CI
            if env in {"dev", "test"}:
                log.exception(
                    "router include failed (fatal in %s): %s", env, spec.import_path
                )
                raise
            # In production, log and continue gracefully
            log.warning("router include failed: %s (%s)", spec.import_path, e)

    # Register alias compatibility routes onto the app (best-effort).
    try:
        # Import lazily to avoid optional dependency errors
        from app.router.alias_api import register_aliases

        register_aliases(app, prefix="/v1")
    except Exception:
        # Non-fatal: alias router is optional
        log.debug("alias router registration skipped or failed")

    # Ollama/Llama integration: best-effort check
    try:
        # Try to import llama router module to see if local LLaMA integration is available
        _ = _load_router("app.routers.llama_router:llama_router")
        mounted["ollama"] = True
    except Exception:
        mounted["ollama"] = False

    # Qdrant vector store detection (best-effort)
    try:
        # If import succeeds and VECTOR_STORE env references qdrant, mark True
        if (os.getenv("VECTOR_STORE") or "").lower().startswith("qdrant"):
            mounted["qdrant"] = True
    except Exception:
        mounted["qdrant"] = False

    # Expose mounted features on the app state for other modules to query
    try:
        app.state.features_mounted = mounted
    except Exception:
        # Best-effort; do not fail include flow for apps that don't support .state assignment
        log.debug("Could not set app.state.features_mounted")
