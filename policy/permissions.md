# Permissions & Hard Rules

These rules are enforced by the selector/executor and cannot be bypassed by
LLM output.

- **Never auto-act**: Locks, doors, purchases, or medication dosage changes
  must never be automatically executed without explicit confirmation.

- **Clamp brightness/volume**: Any requested change must be clamped to
  allowed ranges (0..100). Volume/brightness jumps greater than 20% require
  explicit confirmation.

- **Undo window**: Reversible actions may be undone automatically within a
  short window (e.g., 60 seconds). After the window, undo must be manual.

- **Tool validation**: All LLM-suggested tool invocations must pass
  `validator.validate()` before execution.


