- Retrieval policy: cosine only; keep if similarity ≥ 0.75 (distance ≤ 0.25). Logged with raw scores and kept/dropped counts.
RBAC and Audit

RBAC
- Admin endpoints in `app/api/admin.py` and `app/api/status_plus.py:/admin/backup` now require the `admin` scope when JWTs are enabled, via `optional_require_scope("admin")`.
- Additionally, ADMIN_TOKEN must match when set. In tests, token can be omitted unless explicitly provided.

Writebacks
- Pinned writes in MemGPT emit audit records and include an `audit` marker on interactions.
- Vector store writes and transcripts are PII-redacted before storage; the raw→token substitution map is stored in `data/redactions/` and should be access-controlled.

Audit log
- `app/audit.py` writes an append-only JSONL with a simple hash chain. Use to track pin actions:
  - action: `pin_claim` with checksum and session_id
  - action: `pin_interaction` with hash and session_id

Operating notes
- Set `ENFORCE_JWT_SCOPES=1` to enforce scopes in all environments with JWTs.
- Ensure filesystem permissions restrict access to `data/redactions/` and backups output.
