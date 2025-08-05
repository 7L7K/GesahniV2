"""GesahniV2 application package."""

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
