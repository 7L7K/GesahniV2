"""Router package (kept intentionally empty).

This module is intentionally a no-op package initializer. Heavy router
components live in `app.router` leaf modules (e.g. `app.router.entrypoint`,
`app.router.policy`, `app.router.ask_api`). Keep this file minimal to avoid
import-time side effects and circular imports.

Import router functions directly where needed instead of relying on package exports.

For backward compatibility, some legacy symbols are re-exported from compat.py
"""

# Re-export compatibility symbols for tests and legacy code
from .compat import *
