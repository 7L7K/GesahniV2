Telemetry metrics (names and buckets)

- skill_hits_total{skill}: Counter per skill name.
- selector_latency_ms: Histogram (buckets in ms) e.g. [5,10,25,50,100,250,500,1000,5000]
- skill_conf_bucket{le}: Histogram buckets for confidences: le=0.5,0.6,0.7,0.8,0.9,1.0
- llm_fallback_total: Counter when router falls back to LLM
- undo_invocations_total: Counter when UndoSkill invoked
- entity_disambiguations_total: Counter when resolver returns disambiguation

Log fields to emit per request (consistent with `telemetry.LogRecord`):
- normalized_prompt
- chosen_skill
- confidence
- slots (dict)
- why (skill_why)
- took_ms
- idempotency_key
- deduped (bool)
- skipped_llm (bool)

Dashboard guidance:
- Show top skills by `skill_hits_total` and average `selector_latency_ms`.
- Visualize `skill_conf_bucket` heatmap to find ambiguous ranges.
- Chart `llm_fallback_total` overlapped with `skill_conf_bucket` & `selector_latency_ms` to spot failures.
