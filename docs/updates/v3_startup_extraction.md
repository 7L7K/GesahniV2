# v3 — Startup Extraction (summary)

Date: 2025-09-04

Overview
--------
This update extracts and documents application startup into a dedicated
package `app/startup/`, makes the FastAPI app use the extracted lifespan,
and documents/tests the new behavior. The goal is safer, environment-first
booting and easier Phase 2 refactors (routers/middleware extraction).

Files touched (created/modified)
--------------------------------
- app/startup/__init__.py — new: exported `lifespan`, shutdown helpers, and
  vendor util.
- app/startup/config.py — new: `detect_profile()` and `StartupProfile`.
- app/startup/components.py — new/updated: small async component initializers
  (DB, token schema, OpenAI health, vector store, LLaMA, HA, memory, scheduler)
- app/startup/vendor.py — new: gated vendor health checks (OpenAI, Ollama).
- app/startup.py — deleted (legacy single-file startup moved into package).
- app/main.py — updated to import `lifespan` from `app.startup` and remove the
  inline lifespan implementation (keeps `app = FastAPI(...)` for now).

Docs & developer guidance
-------------------------
- README.md — added developer note about `app/startup/` and acceptance checks.
- AGENTS.md — added `Startup overview` pointing to startup package files.
- CONTRIBUTING.md — added contributor rules for adding/modifying startup
  components and PR checklist items.
- .env.example — documented new env vars: `STARTUP_VENDOR_PINGS`,
  `STARTUP_CHECK_TIMEOUT`, `STARTUP_STEP_TIMEOUT`.
- docs/adr/0001-startup-extraction.md — ADR describing the decision and
  rationale for the extraction.

Tests added
-----------
- tests/unit/test_startup_lifespan_ci.py — verifies `detect_profile()` yields
  `ci` when `CI=1` and that vendor pings are gated.
- tests/unit/test_startup_components.py — basic idempotence and probe tests
  for token store and vector store initializers.

Why we did this
---------------
- Reduce import-time work to make tests and local development faster and more
  reliable.
- Make startup behavior explicit and environment-aware (dev/prod/ci), so CI
  runs a short, deterministic set of components.
- Improve testability by isolating small, idempotent initializers that can be
  exercised independently.
- Prepare codebase for a phased Phase 2: moving routers and middleware out of
  `app/main.py` with minimal risk.

Next steps (Phase 2 prep)
------------------------
- Extract router includes and middleware setup from `app/main.py` into
  dedicated modules.
- Add CI smoke job that imports `app.main` and runs a short startup check.
- Expand unit tests to simulate partial failures and ensure graceful startup
  logging/metrics.

Where to look
-------------
- Startup code: `app/startup/`
- Lifespan wiring: `app/main.py` (now uses `lifespan=app.startup.lifespan`)
- ADR: `docs/adr/0001-startup-extraction.md`
- Tests: `tests/unit/test_startup_*.py`


