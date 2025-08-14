## Observability & Acceptance Checklist

Use this checklist to verify the system is healthy after deployment. These steps focus on the `/v1/ask` flow and the retrieval pipeline.

### Preconditions
- A valid JWT if `REQUIRE_AUTH_FOR_ASK=1` (default).
- Qdrant reachable if using real vector search, or stub embeddings in tests.

### Checks
1) Call `/v1/ask` with a small prompt.
   - Expect HTTP 200 with either `text/event-stream` or `text/plain`.
   - Header `X-Trace-ID` present.
   - Logs contain `ask.entry` then `retrieval.start` then `retrieval.finish` then `ask.success`.

2) Repeat the same `/v1/ask` prompt (exactly identical).
   - Logs include `retrieval.cache_hit` with a small `age_s`.

3) Negative auth sanity (optional in prod, required in staging):
   - Send request without/with bad token; expect HTTP 401 and log `auth.missing_bearer` or `auth.invalid_token`.

### Example “green” log snippets

```
INFO retrieval.start meta={"user_hash": "a1b2...", "intent": "chat", "collection": "kb:default", "query_len": 12}
INFO retrieval.finish meta={"user_hash": "a1b2...", "intent": "chat", "collection": "kb:default", "input_len": 12, "kept": 8, "trace_len": 9, "k_dense": 80, "k_sparse": 80}
INFO ask.success meta={"user_hash": "a1b2...", "streamed": true}
```

If you immediately repeat the same request, also expect:

```
INFO retrieval.cache_hit meta={"user_hash": "a1b2...", "intent": "chat", "collection": "kb:default", "age_s": 0.1, "texts": 8}
```


