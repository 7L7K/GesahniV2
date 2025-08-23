# Label Hygiene & Cardinality Audit

## Current Metrics Analysis

### ✅ Good (Low Cardinality)

**Core HTTP Metrics:**
- `http_requests_total`: labels=(route, method, status)
  - ✅ Routes are templated (e.g., "/v1/csrf", not "/v1/csrf/123")
  - ✅ Method: bounded set (GET, POST, PUT, DELETE, etc.)
  - ✅ Status: bounded set (200, 404, 500, etc.)

- `http_request_latency_seconds`: labels=(route, method)
  - ✅ Same as above

**Auth/RBAC Metrics:**
- `auth_fail_total`: labels=(reason)
  - ✅ Bounded reasons: "missing_token", "expired", "invalid"
- `rbac_deny_total`: labels=(scope)
  - ✅ Bounded scopes from permission system

### ⚠️ Potential Issues (Need Fixing)

**Router Metrics:**
- `ROUTER_REQUESTS_TOTAL`: labels=(vendor, model, reason)
  - ⚠️ `model`: Could be any LLM model name (high cardinality risk)
  - ✅ `vendor`: Bounded ("openai", "ollama")
  - ✅ `reason`: Bounded routing reasons

**TTS Metrics:**
- `TTS_REQUEST_COUNT`: labels=(engine, tier, mode, intent, variant)
  - ⚠️ `variant`: Could be voice names (high cardinality)
  - ⚠️ Multiple dimensions increase explosion risk

**Shape Normalization:**
- `ROUTER_SHAPE_NORMALIZED_TOTAL`: labels=(from_shape, to_shape)
  - ⚠️ `shape`: Could be any string representation

### ❌ High Cardinality Issues Found

**1. Model Labels in Router Metrics**
- Problem: `ROUTER_REQUESTS_TOTAL` uses raw model names
- Risk: New models = new time series
- Current models: gpt-4o, gpt-4, gpt-3.5-turbo, llama2:7b, etc.

**2. Voice Variants in TTS**
- Problem: `TTS_REQUEST_COUNT` uses voice names as variants
- Risk: New voices = new time series

**3. Shape Strings**
- Problem: Shape normalization uses raw string representations
- Risk: Any change in request structure = new series

## Recommended Fixes

### 1. Normalize Model Labels
Instead of raw model names, use normalized labels:
- gpt-4o, gpt-4-turbo → "gpt4"
- gpt-3.5-turbo → "gpt35"
- llama2:7b, llama3:8b → "llama"

### 2. Reduce TTS Label Dimensions
- Remove `variant` label or normalize it
- Consider separate metrics for different use cases

### 3. Hash or Categorize Shapes
- Use shape categories instead of raw strings
- Or remove this metric if not essential

## Implementation Plan

1. **Audit all metric usage** in codebase
2. **Create normalized label functions**
3. **Update metric calls** to use normalized labels
4. **Add validation** to prevent high cardinality labels
5. **Document cardinality limits** for future metrics

## Cardinality Limits

- **Routes**: < 50 unique values (templated, not raw paths)
- **Scopes**: < 20 unique values (bounded permission set)
- **Reasons**: < 10 unique values per metric
- **Models**: < 5 normalized categories
- **Status codes**: < 10 HTTP status codes
- **Methods**: < 5 HTTP methods

## Monitoring

To monitor cardinality growth:
1. Check `/api/v1/label/__name__/values` in Prometheus
2. Use `count_values()` function on labels
3. Set up alerts for unexpected label growth
4. Regular audits of top cardinality series
