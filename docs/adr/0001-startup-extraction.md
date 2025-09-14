# 0001 - Extract application startup into `app/startup/`

Date: 2025-09-04

Status: Accepted

Context
-------

Historically the FastAPI application performed a large amount of boot-time
initialization inline in `app/main.py`. This included DB schema initialization,
vendor health checks (OpenAI/Ollama), vector store probes, scheduler startup,
and optional Home Assistant checks. This led to a few issues:

- Heavy work at import time made testing and local development slower and more
  brittle.
- Hard to reason about which components run in `dev` vs `prod` vs `ci`.
- Large single-file boot logic discouraged reuse and made phased extraction
  risky.

Decision
--------

We extracted startup behavior into a small package `app/startup/` with the
following files:

- `config.py`: profile detection (`dev`/`prod`/`ci`) and deterministic ordered
  lists of components to run.
- `components.py`: small async initializer functions (DB, token schema, OpenAI
  health, vector store, LLaMA, HA, memory store, scheduler). These are designed
  to be idempotent, quick, and tolerant of optional misconfiguration.
- `vendor.py`: gated vendor health checks for OpenAI and Ollama.
- `__init__.py`: exposes a reusable `lifespan` asynccontextmanager that the
  FastAPI app uses via `lifespan=app.startup.lifespan`.

Rationale
---------

- Environment-first: `config.detect_profile()` makes it explicit which
  components run in each profile. `CI` runs a minimal set to keep tests fast.
- Testability: Small, pure-ish initializers can be exercised in unit tests and
  are less likely to produce side effects during import-time testing.
- Incremental refactor: `app/main.py` retains router and middleware wiring for
  now; we only replaced the lifespan. This keeps risk low and simplifies a
  phased migration plan.

Consequences
------------

- Startup is now orchestrated by `app/startup.lifespan` which runs component
  initializers under timeouts and logs structured progress lines.
- New environment variables were introduced: `STARTUP_VENDOR_PINGS`,
  `STARTUP_CHECK_TIMEOUT`, and `STARTUP_STEP_TIMEOUT`. They are documented in
  `.env.example`.
- Future work: Phase 2 will extract router and middleware composition from
  `app/main.py` into separate modules and add CI smoke steps to validate
  startup behavior automatically.
