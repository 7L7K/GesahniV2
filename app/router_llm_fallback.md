# LLM Fallback: Strict, Schema-first Escalation

This doc describes the router's escalation path when the deterministic selector
cannot confidently choose a builtin skill.

1) Trigger
- If the selector's top score < WEAK_BAND_LO (policy threshold) but >= NO_MATCH
  band, the router may allow a single LLM turn to attempt to produce a tool
  invocation. The router will only allow one LLM generation for ambiguity.

2) Tool-first prompt
- The router invokes the LLM with a constrained prompt asking for a tool name
  from `app/skills/tools/catalog.py` and a slots JSON object matching the tool
  schema. The prompt enforces that the model must not produce free-form text
  for actions — only structured tool calls are allowed.

3) Validate
- The router passes the returned slots to `app/skills/tools/validator.validate()`.
- If validation passes, the router executes the mapped skill/tool using the
  same idempotency and ledger recording rules as deterministic skills.
- If validation fails, the router returns a short clarification question to the
  user indicating the exact missing or ambiguous fields (no hallucination).

4) Safety
- Tools that would change state require STRONG_MATCH unless the LLM tool call
  is validated and the selector allowed one escalation.
- Volume/brightness jumps >20% must trigger an explicit confirmation.

5) Auditing
- All tool executions are written to the ledger via `record_action()` with a
  deterministic idempotency key. LLM-assisted actions must be auditable and
  reversible where supported.

6) Limits
- One LLM call per ambiguous request. If the LLM cannot produce a valid tool
  call in one turn, router declines and suggests manual clarification.

Acceptance
- Messy phrasing can be handled in a single safe LLM turn that returns a
  structured tool call, which is validated and executed deterministically.
