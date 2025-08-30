System Conventions (Locked)

1) Error Envelope (every endpoint)
- code: machine-readable short code (e.g., needs_reconnect, scopes_missing, quota, account_mismatch, invalid_state, token_expired)
- message: concise human message
- hint: actionable suggestion (optional)
- details: debuggable context (req_id, trace_id, path, method, status_code, and any safe extras)

2) Structured Log Keys
- provider: third-party provider (e.g., google, spotify)
- service: logical service/component name
- sub: provider user subject (OIDC sub when present)
- req_id: request id propagated across logs
- trace_id: OpenTelemetry trace id (hex)
- status_code: HTTP status code
- latency_ms: request latency in milliseconds
- error_code: compact category code for 4xx/5xx

3) Token Row Truth
- One row per (user_id × Google sub)
- Columns: provider, provider_sub, scope (unioned), service_state (JSON string), validity flags and timestamps
- No duplicates, no per-service token rows; upserts must union scopes when reauthorizing

4) UI Toggle Semantics
- Optimistic UI OFF by default for auth-gated actions
- Only flip UI state after backend confirmation, or auto-rollback with a toast that surfaces the error envelope

Notes
- Backend enforces the error envelope via FastAPI exception handlers and middleware.
- Logging formatter lifts structured keys from log records into top-level JSON fields.
- Token DAO adds provider_sub/service_state columns and unions scopes on upsert.
