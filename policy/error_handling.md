# Error Handling & User-facing Messages

User-facing behavior rules for failures:

- Keep messages short, kind, and specific. Example: "I couldn't find that
  device—did you mean living room light or hallway light?"

- Prefer no-op over risky best-guess. If validation fails, ask for the
  missing/ambiguous slot instead of guessing and acting.

- For downstream failures (HA unavailable), report a short failure and
  optionally enqueue an offline retry if the action is non-urgent.

- Log full diagnostic details internally but never surface PII in the
  short user-facing message.
