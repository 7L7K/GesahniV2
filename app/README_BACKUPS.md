## Profile facts (KV) and Qdrant recall policy

- Profile facts canonical keys: `preferred_name, favorite_color, timezone, locale, home_city, clothing_sizes, music_service, commute_home, device_ids, calendars_connected`.
- Upsert rule: newest wins; single row per key per user; store `updated_at` and `source`.
- Read path: simple classifier routes profile questions to KV-only. If a requested key exists, answer directly. Minimal `[USER_PROFILE_FACTS]` block is injected for visibility and a blunt KV-wins instruction is appended to system instructions.
- Vector recall: Qdrant with cosine metric. Keep only results with similarity ≥ 0.75 (distance ≤ 0.25). Logged with raw scores, threshold, and kept/dropped counts.
- Prompt diet: small asks use facts block only; no long history; sub-200 tokens in practice.
Encrypted backups at rest

Overview
- Backups are created via the POST /v1/admin/backup endpoint (requires admin scope and ADMIN_TOKEN).
- Contents: data/*.json, stories/*.jsonl, sessions/archive/*.tar.gz (if present).
- Output directory: BACKUP_DIR (defaults to app/backups/).
- Encryption: AES-256-CBC using OpenSSL with PBKDF2. Fallback to XOR+base64 if OpenSSL is unavailable.

Environment
- BACKUP_KEY: required secret passphrase used to encrypt the tarball.
- BACKUP_DIR: optional, target directory for backup artifacts.

Key rotation
- Rotate BACKUP_KEY by:
  1. Setting a new BACKUP_KEY value.
  2. Trigger a fresh backup to produce a new encrypted archive with the new key.
  3. Optionally decrypt old backups with the old key and re-encrypt using the new key for consistency.

Decrypting
- With OpenSSL:
  openssl enc -d -aes-256-cbc -pbkdf2 -pass pass:$BACKUP_KEY -in backup.tar.gz.enc -out backup.tar.gz

Security notes
- BACKUP_KEY must be managed in your secret store and never checked into version control.
- The redaction substitution maps are stored in data/redactions/ and are included in backups; access to backups must be restricted to trusted operators.



### Observability notes

- Logs are structured JSON with `req_id` and `trace_id` for correlation.
- Prometheus metrics are available at `/metrics` when `PROMETHEUS_ENABLED=1`.
- OpenTelemetry tracing can be enabled via environment:
  - `OTEL_ENABLED=1`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` (or your collector)
  - Optional: `OTEL_SERVICE_NAME=gesahni`, `OTEL_SERVICE_VERSION=dev`

