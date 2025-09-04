"""Router package (kept intentionally empty).

This module is intentionally a no-op package initializer. Heavy router
components live in `app.router` leaf modules (e.g. `app.router.entrypoint`,
`app.router.policy`, `app.router.ask_api`). Keep this file minimal to avoid
import-time side effects and circular imports.
"""

__all__: list[str] = []