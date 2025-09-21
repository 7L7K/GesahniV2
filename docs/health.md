Health Endpoints and Frontend UX

This project implements tiered health probes and a degraded-mode indicator.

Endpoints

- Live: `/healthz/live`
  - Returns `200 {"status":"ok"}` if process is up.
  - No I/O, no deps, no DB.

- Ready: `/healthz/ready`
  - Core readiness only. Required checks (each 500ms timeout via `with_timeout`):
    - `check_jwt_secret()`
    - `check_db()` (session/user store)
  - Any required failure → `503 {"status":"fail","failing":["db",...]}`
  - All pass → `200 {"status":"ok"}`

- Deps: `/healthz/deps`
  - Optional checks (non-blocking), each timeboxed 500ms:
    - `check_llama()` (env: `OLLAMA_URL` or `LLAMA_URL`, GET probe)
    - `check_home_assistant()` (env: `HOME_ASSISTANT_URL`)
    - `check_qdrant()` (env: `QDRANT_URL`)
    - `check_spotify()` (enabled when `GSNH_ENABLE_SPOTIFY=1`)
  - Missing env → `"skipped"`. Failure → `"error"`.
  - Response:
    {
      "status": "ok|degraded",
      "checks": { "backend":"ok", "llama":"error", "ha":"skipped", "qdrant":"ok", "spotify":"skipped" }
    }
  - `status` is `degraded` iff any check is `error`.

- Metrics: `/metrics`
  - Exposes Prometheus metrics including `gesahni_requests_total`, `gesahni_latency_seconds_*`, and `gesahni_llama_queue_depth` (0 if N/A).

Frontend behavior

- Blocking banner probes `/healthz/ready` every 3s with:
  - `credentials: 'omit'`, `cache: 'no-store'`, `signal: AbortSignal.timeout(2000)`.
  - Shows “Backend offline — retrying…” until `status === "ok"`.

- Degraded icon probes `/healthz/deps` every ~10s with the same fetch options.
  - If `status === "degraded"`, shows a small warning listing failing checks.
  - Never blocks chat/input.

Environment knobs

- OLLAMA_URL, LLAMA_URL – enable LLaMA probe
- HOME_ASSISTANT_URL – enable HA probe
- QDRANT_URL – enable Qdrant probe
- GSNH_ENABLE_SPOTIFY=1 – enable Spotify probe

Examples

- `/healthz/live` → `{ "status": "ok" }`
- `/healthz/ready` → `{ "status": "ok" }` or `{ "status": "fail", "failing": ["db"] }`
- `/healthz/deps` → `{ "status": "degraded", "checks": { "backend": "ok", "llama": "error", "ha": "skipped", "qdrant": "ok", "spotify": "skipped" } }`
