"""GesahniV2 application package."""

# Ensure a default asyncio event loop exists in the main thread during tests
# and simple import contexts that call asyncio.get_event_loop().
import asyncio

# Avoid deprecated get_event_loop() probe on import in Python 3.12+.
# If no running loop exists, install a fresh default loop so modules that
# assume a default loop (e.g., tests) continue to work without warnings.
try:  # pragma: no cover - environment bootstrap
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# Access to ``app.skills`` pulls in a large collection of modules, some of which
# depend on optional third‑party packages.  Importing it unconditionally makes
# simple operations like ``import app`` fragile.  Instead we expose ``skills``
# lazily via ``__getattr__`` so that it is only imported when explicitly
# requested (e.g. ``from app import skills``).

import importlib
from types import ModuleType
from typing import Any

__all__ = ["skills"]


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial
    if name == "skills":
        module: ModuleType = importlib.import_module(".skills", __name__)
        globals()[name] = module
        return module
    # Provide backward-compatible `app.audit` package import for tests that
    # expect `app.audit.models` and `app.audit.store` to be importable. If the
    # real `app.audit` package exists on disk it will be used; otherwise we map
    # the legacy `app.audit_legacy` module into `app.audit` so imports like
    # `from app.audit.models import AuditEvent` can succeed during tests.
    if name == "audit":
        try:
            module: ModuleType = importlib.import_module(".audit", __name__)
            globals()[name] = module
            return module
        except Exception:
            legacy_module: ModuleType = importlib.import_module(
                ".audit_legacy", __name__
            )
            # Create a simple package-like object that re-exports commonly used
            # names from the legacy module.
            pkg = ModuleType("app.audit")
            # Re-export functions and constants used by tests
            for attr in (
                "append_audit",
                "append_ws_audit",
                "append_http_audit",
                "get_audit_events",
                "verify_audit_integrity",
                "AUDIT_EVENT_TYPES",
            ):
                if hasattr(legacy_module, attr):
                    setattr(pkg, attr, getattr(legacy_module, attr))
            globals()[name] = pkg
            return pkg
    raise AttributeError(name)
