# Daily Digest Job

Plan for a daily summarization job:

- Run once per day (configurable time).
- Aggregate:
  - transcripts (if any) and recent ledger actions.
  - notes and check-ins.
- Produce:
  - Structured bullets: who/what/when counts.
  - Candidate routines (sequence-like repeated actions).
  - Candidate aliases (stable phrase→entity mappings).
- Output:
  - Write a small summary record consumed by `DaySummarySkill`.
  - Push candidate suggestions into `SuggestionsSkill` via `push_suggestion()`.

Privacy & retention:
- Keep digest local only; honor PII redaction settings.
