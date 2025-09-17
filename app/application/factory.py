from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.application.config import TAGS_METADATA, derive_version, load_openapi_config
from app.application.diagnostics import build_diagnostics_router, prepare_snapshots
from app.env_utils import load_env
from app.startup import lifespan

logger = logging.getLogger(__name__)


def build_application() -> FastAPI:
    """Assemble the FastAPI application with routers, middleware, and diagnostics."""
    load_env()
    logger.info("🔧 Starting application composition in build_application()")

    debug_startup = os.getenv("GSN_DEBUG_STARTUP") == "1"
    if debug_startup:
        _enable_fault_handler()

    openapi_config = load_openapi_config()
    app = FastAPI(
        title="GesahniV2",
        version=derive_version() or os.getenv("APP_VERSION", ""),
        lifespan=lifespan,
        openapi_tags=TAGS_METADATA,
        docs_url=openapi_config.get("docs_url"),
        redoc_url=openapi_config.get("redoc_url"),
        openapi_url=openapi_config.get("openapi_url"),
        swagger_ui_parameters=openapi_config.get("swagger_ui_parameters"),
    )

    if debug_startup:
        _instrument_debug_tracing(app)

    _register_routers(app)
    _include_dev_router(app)
    _include_spotify_routers(app)
    _ensure_health_route(app)

    _initialize_infrastructure()
    _configure_router_registry()
    _register_backend_factories()
    _configure_middlewares(app)
    _enforce_strict_vector_store()
    _register_test_error_router(app)
    _setup_openapi(app)
    _mount_static_assets(app)

    prepare_snapshots(app, debug=debug_startup)
    if os.getenv("ENV", "dev").lower() in {"dev", "local", "test", "ci"}:
        app.include_router(build_diagnostics_router(debug=debug_startup))

    _check_route_collisions(app)
    _register_error_handlers(app)

    logger.info("🎉 Application composition complete in build_application()")
    return app


def _enable_fault_handler() -> None:
    import faulthandler
    import sys

    faulthandler.dump_traceback_later(8, repeat=True, file=sys.stderr)


def _instrument_debug_tracing(app: FastAPI) -> None:
    from app.diagnostics.startup_probe import probe
    from app.diagnostics.state import record_event, record_router_call, set_snapshot

    set_snapshot("before", probe(app))
    record_event("app-created", "FastAPI instantiated")

    original_include = app.include_router

    def _trace_include(router, *args, **kwargs):
        prefix = kwargs.get("prefix")
        try:
            where = f"{router.tags if hasattr(router, 'tags') else ''}"
        except Exception:
            where = "<router>"
        result = original_include(router, *args, **kwargs)
        record_router_call(
            where=str(where), prefix=prefix, routes_total=len(app.routes)
        )
        return result

    app.include_router = _trace_include  # type: ignore[assignment]


def _register_routers(app: FastAPI) -> None:
    from app.routers.config import register_routers

    dev_env = os.getenv("ENV", "dev").lower() in {"dev", "test", "ci"}
    try:
        register_routers(app)
    except Exception as exc:
        if dev_env:
            raise
        logger.exception("Router registration failed; continuing (prod): %s", exc)
        return

    if dev_env:
        _assert_required_auth_routes(app)


def _assert_required_auth_routes(app: FastAPI) -> None:
    paths = {getattr(route, "path", None) for route in app.routes}
    required = {
        "/v1/auth/whoami",
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/refresh",
        "/v1/auth/logout",
    }
    missing = sorted(path for path in required if path not in paths)
    assert not missing, f"Auth routes missing after registration: {missing}"


def _include_dev_router(app: FastAPI) -> None:
    env = os.getenv("ENV", "dev").lower()
    if env not in {"dev", "local"}:
        return

    try:
        from app.api.dev import router as dev_router

        app.include_router(dev_router, prefix="/dev", tags=["Dev"])
    except Exception as exc:
        logger.warning("Failed to include dev router: %s", exc)


def _include_spotify_routers(app: FastAPI) -> None:
    try:
        from app.api.spotify import integrations_router as spotify_integrations_router
        from app.api.spotify import router as spotify_router
    except Exception as exc:
        logger.warning("Failed to import Spotify routers: %s", exc)
        return

    if getattr(app.state, "spotify_mounted", False):
        logger.debug("Spotify routers already mounted (state flag)")
        return

    existing_paths = {getattr(route, "path", None) for route in app.routes}
    spotify_paths = {"/v1/spotify/callback", "/v1/integrations/spotify/status"}
    if any(path in existing_paths for path in spotify_paths):
        logger.debug("Spotify routers already mounted by router mounting system")
        app.state.spotify_mounted = True
        return

    try:
        app.include_router(spotify_router, prefix="/v1")
        app.include_router(spotify_integrations_router, prefix="/v1")
        logger.debug(
            "✅ Spotify routers mounted at /v1/spotify and /v1/integrations/spotify"
        )
        app.state.spotify_mounted = True
    except Exception as exc:
        logger.warning("Failed to include Spotify routers: %s", exc)


def _ensure_health_route(app: FastAPI) -> None:
    paths = {getattr(route, "path", None) for route in app.routes}
    if "/healthz" in paths:
        return

    from fastapi import APIRouter

    probe_router = APIRouter()

    @probe_router.get("/healthz", include_in_schema=False)
    async def _healthz_probe() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(probe_router)
    logger.info("Mounted fallback /healthz endpoint")


def _initialize_infrastructure() -> None:
    try:
        from app.infra.model_router import init_model_router
        from app.infra.oauth_monitor import init_oauth_monitor
        from app.infra.router_rules import init_router_rules_cache

        init_model_router()
        init_router_rules_cache()
        init_oauth_monitor()
        logger.debug("✅ Infrastructure singletons initialized")
    except Exception as exc:
        logger.warning("⚠️  Failed to initialize infrastructure singletons: %s", exc)


def _configure_router_registry() -> None:
    try:
        from app.bootstrap.router_registry import configure_default_router

        configure_default_router()
        logger.debug("✅ Router configured via bootstrap registry")
    except Exception as exc:
        logger.warning("⚠️  Failed to configure router: %s", exc)


def _register_backend_factories() -> None:
    try:
        from app.routers import normalize_backend_name, register_backend_factory

        def _backend_factory(name: str):
            normalized = normalize_backend_name(name)
            if normalized == "openai":
                from app.routers.openai_router import openai_router

                return openai_router
            if normalized == "llama":
                from app.routers.llama_router import llama_router

                return llama_router
            if normalized == "dryrun":
                from app.routers.dryrun_router import dryrun_router

                return dryrun_router

            async def _unknown_backend(payload: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError(f"Unknown backend: {name}")

            return _unknown_backend

        register_backend_factory(_backend_factory)
        logger.debug("✅ Backend factory registered (openai/llama/dryrun)")
    except Exception as exc:
        logger.warning("⚠️  Failed to register backend factory: %s", exc)


def _configure_middlewares(app: FastAPI) -> None:
    from app.middleware.loader import register_canonical_middlewares
    from app.settings_cors import get_cors_origins

    csrf_enabled = bool(int(os.getenv("CSRF_ENABLED", "1")))
    cors_origins = get_cors_origins()
    register_canonical_middlewares(
        app, csrf_enabled=csrf_enabled, cors_origins=cors_origins
    )
    logger.debug("✅ Canonical middleware stack configured")
    _validate_middleware_order(app)


def _enforce_strict_vector_store() -> None:
    strict_vs = (os.getenv("STRICT_VECTOR_STORE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not strict_vs:
        return

    from app.memory.unified_store import create_vector_store

    create_vector_store()


def _register_test_error_router(app: FastAPI) -> None:
    try:
        from app.test_error_normalization import router as test_router

        app.include_router(test_router, prefix="/test-errors", tags=["test-errors"])
        logger.info("✅ Test error normalization router registered at /test-errors")
    except ImportError as exc:
        logger.warning("⚠️  Failed to import test router: %s", exc)
    except Exception as exc:
        logger.warning("⚠️  Failed to register test router: %s", exc)


def _setup_openapi(app: FastAPI) -> None:
    try:
        from app.openapi.generator import setup_openapi_for_app

        setup_openapi_for_app(app)
        logger.debug("✅ OpenAPI generation configured")
    except Exception as exc:
        logger.warning("⚠️  Failed to set up OpenAPI generation: %s", exc)


def _mount_static_assets(app: FastAPI) -> None:
    try:
        tv_dir = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
        if tv_dir:
            app.mount(
                "/shared_photos",
                StaticFiles(directory=tv_dir, html=False, follow_symlink=False),
                name="shared_photos",
            )
    except Exception:
        pass

    try:
        album_dir = os.getenv("ALBUM_ART_DIR", "data/album_art")
        if album_dir:
            Path(album_dir).mkdir(parents=True, exist_ok=True)
            app.mount(
                "/album_art",
                StaticFiles(directory=album_dir, html=False, follow_symlink=False),
                name="album_art",
            )
    except Exception:
        pass


def _check_route_collisions(app: FastAPI) -> None:
    pair_to_handlers: dict[tuple[str, str], list[str]] = defaultdict(list)

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not methods or not path:
            continue

        try:
            qualname = f"{endpoint.__module__}.{endpoint.__qualname__}"
        except Exception:
            qualname = repr(endpoint)

        for method in methods:
            if method == "HEAD":
                continue
            pair_to_handlers[(method, path)].append(qualname)

    duplicates: dict[tuple[str, str], list[str]] = {}
    for pair, handlers in pair_to_handlers.items():
        if len(handlers) <= 1:
            continue
        compat_handlers = [handler for handler in handlers if "compat_api" in handler]
        non_compat_handlers = [
            handler for handler in handlers if "compat_api" not in handler
        ]
        if len(non_compat_handlers) > 1:
            duplicates[pair] = handlers
        elif len(compat_handlers) > 0 and len(non_compat_handlers) == 1:
            continue
        else:
            duplicates[pair] = handlers

    if duplicates:
        lines = [f"Duplicate route registrations detected ({len(duplicates)}):"]
        for (method, path), handlers in sorted(duplicates.items()):
            lines.append(f" - {method} {path}:\n    " + "\n    ".join(handlers))
        message = "\n".join(lines)
        logger.warning(message)
        if os.getenv("ENV", "dev").lower() in {"dev", "test", "ci"}:
            raise RuntimeError(message)


def _validate_middleware_order(app: FastAPI) -> None:
    env = os.getenv("ENV", "dev").lower()
    if env not in {"dev", "test", "ci"}:
        return

    middleware_names = [mw.cls.__name__ for mw in app.user_middleware]
    if "CORSMiddleware" in middleware_names and "CSRFMiddleware" in middleware_names:
        csrf_idx = middleware_names.index("CSRFMiddleware")
        cors_idx = middleware_names.index("CORSMiddleware")
        # CSRF should come before CORS in the stored middleware list (executes before CORS)
        if csrf_idx > cors_idx:
            raise RuntimeError(
                "CSRFMiddleware must execute before CORSMiddleware (add CSRF after CORS in code)"
            )


def _register_error_handlers(app: FastAPI) -> None:
    from app.error_handlers import register_error_handlers

    register_error_handlers(app)


__all__ = ["build_application"]
