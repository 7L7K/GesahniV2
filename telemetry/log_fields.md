# Required log fields for skill actions

Every recorded skill action (history/telemetry) must include the following
fields for auditability and debugging. They should be written into the
`LogRecord` emitted to `data/history.jsonl`.

- `normalized_prompt`: string — the normalized prompt used for matching
- `chosen_skill`: string — skill class name chosen (or null)
- `confidence`: float — selected/confidence score used by selector
- `slots`: JSON/dict — extracted slots (canonical types)
- `why`: string — short human-readable reason (non-sensitive)
- `took_ms`: int — elapsed time in milliseconds to run selection+skill
- `idempotency_key`: string|null — opaque key used to dedupe side-effects
- `skipped_llm`: bool — true when LLM was intentionally skipped

Notes:
- `why` must be concise and should not contain PII. Use slot references
  instead of raw user text where possible.
- `slots` should contain canonical types (datetimes ISO8601, ints, etc.)
