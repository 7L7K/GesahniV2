from __future__ import annotations

"""Compatibility shim for `app.audit`.

This module ensures imports like `from app.audit.models import AuditEvent` and
`from app.audit.store import append` work by delegating to `app.audit_new` when
available, or falling back to `app.audit_legacy` otherwise. It registers
`app.audit.models` and `app.audit.store` into `sys.modules` so the rest of the
codebase can import them as normal submodules.
"""

import importlib
import sys
import types
from types import ModuleType


def _load_modules() -> tuple[ModuleType, ModuleType]:
    """Attempt to load (models_module, store_module).

    Prefer `app.audit_new.*` modules; if unavailable, fall back to
    `app.audit_legacy` and expose compatible wrappers.
    """
    # Attempt to prefer the new package but ensure we always register the
    # `app.audit.models` module first to satisfy import order expectations by
    # callers that import models before store.
    try:
        models_mod = importlib.import_module("app.audit_new.models")
    except Exception:
        # Build models module from legacy or fallback
        try:
            legacy = importlib.import_module("app.audit_legacy")
            models_mod = types.ModuleType("app.audit.models")
            if hasattr(legacy, "AuditEvent"):
                models_mod.AuditEvent = legacy.AuditEvent
            else:
                new_models = importlib.import_module("app.audit_new.models")
                models_mod.AuditEvent = new_models.AuditEvent
        except Exception:
            # Last-resort minimal implementation
            from datetime import datetime

            models_mod = types.ModuleType("app.audit.models")

            class AuditEvent:
                def __init__(self, **kwargs):
                    self.ts = datetime.utcnow()
                    for k, v in kwargs.items():
                        setattr(self, k, v)

                def model_dump_json(self):
                    import json

                    return json.dumps(self.__dict__)

            models_mod.AuditEvent = AuditEvent

    # Register models module early so subsequent imports of store can import it
    sys.modules["app.audit.models"] = models_mod

    # Now try to load store module, preferring the new package
    try:
        store_mod = importlib.import_module("app.audit_new.store")
        return models_mod, store_mod
    except Exception:
        try:
            legacy = importlib.import_module("app.audit_legacy")
            store_mod = types.ModuleType("app.audit.store")
            for name in (
                "append",
                "bulk",
                "get_audit_file_path",
                "get_audit_file_size",
                "append_audit",
                "append_ws_audit",
                "append_http_audit",
                "get_audit_events",
                "verify_audit_integrity",
                "AUDIT_EVENT_TYPES",
            ):
                if hasattr(legacy, name):
                    setattr(store_mod, name, getattr(legacy, name))
            return models_mod, store_mod
        except Exception:
            # Final fallback: empty store module
            store_mod = types.ModuleType("app.audit.store")
            return models_mod, store_mod


# Load and register modules
_models_mod, _store_mod = _load_modules()
sys.modules["app.audit.models"] = _models_mod
sys.modules["app.audit.store"] = _store_mod

# Re-export common names for `from app.audit import append_audit` style imports
for _name in (
    "append_audit",
    "append_ws_audit",
    "append_http_audit",
    "get_audit_events",
    "verify_audit_integrity",
    "AUDIT_EVENT_TYPES",
):
    if hasattr(_store_mod, _name):
        globals()[_name] = getattr(_store_mod, _name)
    else:
        # Map common legacy names to nearest equivalents in the new API
        if _name == "append_audit" and hasattr(_store_mod, "append"):
            globals()["append_audit"] = _store_mod.append
        if _name == "append_ws_audit" and hasattr(_store_mod, "append"):
            globals()["append_ws_audit"] = _store_mod.append
        if _name == "append_http_audit" and hasattr(_store_mod, "append"):
            globals()["append_http_audit"] = _store_mod.append

if hasattr(_models_mod, "AuditEvent"):
    AuditEvent = _models_mod.AuditEvent

# Make modules available in the namespace for __all__
models = _models_mod
store = _store_mod

__all__ = ["models", "store", "AuditEvent"]
