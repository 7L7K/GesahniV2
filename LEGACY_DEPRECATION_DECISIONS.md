# Legacy Deprecation Decisions

## Decision: 307 Temporary Redirect for Legacy Routes

**Date**: 2025-09-13
**Status**: Active
**Revisit Date**: 2026-03-13

### Context
When implementing legacy route redirects for backward compatibility during the music HTTP API migration, we needed to choose between HTTP redirect status codes.

### Options Considered

#### Option 1: 302 Found (Temporary Redirect)
- **Pros**: Simple, widely supported
- **Cons**: Some clients may cache as 303, potentially breaking POST requests

#### Option 2: 307 Temporary Redirect (Chosen)
- **Pros**:
  - Preserves request method (GET→GET, POST→POST)
  - Explicit about temporariness
  - RFC 7231 compliant
  - No body modification or method changing
- **Cons**: Slightly less common than 302

#### Option 3: 301 Moved Permanently
- **Pros**: Clear permanent redirect signal
- **Cons**: Not appropriate for temporary legacy support during migration

### Decision
Use **307 Temporary Redirect** for all legacy route redirects because:

1. **Method Preservation**: Critical for APIs where clients might use POST/PUT/DELETE
2. **Explicit Temporariness**: Signals this is a temporary compatibility layer
3. **RFC Compliance**: Follows HTTP standards correctly
4. **Client Compatibility**: Modern HTTP clients handle 307 correctly

### Implementation
```python
@redirect_router.get("/legacy/state", include_in_schema=True, deprecated=True)
async def legacy_music_state_redirect():
    """Redirect legacy /v1/legacy/state calls to new /v1/state endpoint."""
    return RedirectResponse(url="/v1/state", status_code=307)
```

### Revisit Criteria
- Monitor `legacy_hits_total` metric usage
- Revisit if 307 causes client compatibility issues
- Consider moving to 301 after deprecation period if routes become permanent redirects

---

## Decision: Legacy Route Kill Date

**Date**: 2025-09-13
**Kill Date**: 2026-03-13 (6 months)
**Kill Criteria**: `legacy_hits_total == 0` for 30 consecutive days

### Context
Need to establish a timeline for removing legacy routes while providing adequate migration time for clients.

### Timeline
- **Deprecation Date**: 2025-09-13 (Today)
- **Grace Period**: 6 months
- **Kill Date**: 2026-03-13
- **Early Kill**: If `legacy_hits_total == 0` for 30 consecutive days

### Kill Criteria
Routes may be removed **before** the kill date if:
1. No hits recorded in `legacy_hits_total` metric for 30 consecutive days
2. All known clients have migrated to new endpoints
3. No production incidents reported from route removal

### Pre-Kill Checklist
- [ ] Monitor `legacy_hits_total` in Grafana dashboard
- [ ] Notify API consumers via release notes
- [ ] Update client libraries and documentation
- [ ] Run integration tests without legacy routes enabled
- [ ] Verify no production dependencies on legacy endpoints

### Post-Kill Actions
- [ ] Remove `LEGACY_MUSIC_HTTP` feature flag
- [ ] Delete `LegacyHeadersMiddleware`
- [ ] Remove legacy route implementations
- [ ] Update DEPRECATIONS.md to reflect completed migration
- [ ] Update CHANGELOG.md with removal notice

### Monitoring
Track legacy usage via:
- `legacy_hits_total{endpoint="/v1/legacy/state"}` - Hits per endpoint
- `legacy_hits_total{endpoint="/state"}` - Hits per endpoint
- Grafana dashboard: "Legacy Route Usage (last 30d)"

### Contact
For questions about this decision, refer to the DEPRECATIONS.md policy document.
