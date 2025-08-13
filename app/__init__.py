"""GesahniV2 application package."""

# Ensure a default asyncio event loop exists in the main thread during tests
# and simple import contexts that call asyncio.get_event_loop().
import asyncio
try:  # pragma: no cover - environment bootstrap
    asyncio.get_event_loop()
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
    raise AttributeError(name)
