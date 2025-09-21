# Auth Shim Deprecation Guide

## Overview

The `app.api.auth` module has been converted to a deprecation shim that forwards all requests to canonical endpoints in `app.auth.endpoints.*`. This document outlines the deprecation timeline and migration path.

## Current Status

- ✅ **Phase 1 Complete**: Auth shim implemented with deprecation warnings
- 🔄 **Phase 2 Active**: Monitoring deprecated usage with metrics
- ⏳ **Phase 3 Planned**: Sunset flag to break legacy imports (2 sprints)

## Migration Path

### For New Code
**Always import from canonical endpoints:**
```python
# ✅ CORRECT - Use canonical endpoints
from app.auth.endpoints.login import login
from app.auth.endpoints.logout import logout
from app.auth.endpoints.refresh import refresh
from app.auth.endpoints.debug import whoami

# ❌ WRONG - Don't use legacy shim
from app.api.auth import login  # Deprecated!
```

### For Existing Code
**Legacy imports still work but show deprecation warnings:**
```python
# ⚠️ DEPRECATED - Still works but warns
from app.api.auth import login  # Shows deprecation warning
```

## Deprecation Timeline

### Phase 1: Warning Period (Current)
- Legacy imports show deprecation warnings
- All functionality preserved
- Metrics track deprecated usage

### Phase 2: Monitoring Period (Next Week)
- Prometheus metrics alert on high deprecated usage
- Grafana dashboard shows migration progress
- Team notified of remaining legacy usage

### Phase 3: Sunset Period (2 Sprints)
- `BREAK_LEGACY_AUTH_IMPORTS=1` breaks all legacy imports
- Legacy code must be migrated to canonical endpoints
- Final cleanup of deprecated shim

## Monitoring & Metrics

### Prometheus Metrics
- `deprecated_imports_total{module, symbol, call_type}` - Tracks deprecated usage
- `whoami_requests_total{source, jwt_status, authenticated}` - Auth request tracking
- `whoami_latency_seconds{source, jwt_status}` - Performance monitoring

### Grafana Dashboard
- Deprecated imports over time
- Migration progress by module
- Performance impact of shim forwarding

### Alerts
- High deprecated usage (>N/day)
- Performance degradation
- Sunset flag activation

## Technical Details

### Shim Implementation
The shim uses `_DeprecatedAccess` wrapper that:
- Emits deprecation warnings on first access
- Tracks metrics for monitoring
- Forwards all calls to canonical endpoints
- Maintains backward compatibility

### Router Protection
Hard guard prevents router wrapping:
```python
assert "fastapi.routing.APIRouter" in str(type(router)), "router must not be wrapped/proxied"
```

### CI Checks
Automated checks ensure shim integrity:
- No route decorators in shim
- No function implementations
- Router guard present
- Deprecation warning present

## Testing

### Unit Tests
- Forwarding verification
- Deprecation warning emission
- Router guard protection
- Sunset flag functionality

### Integration Tests
- No duplicate routes in OpenAPI
- All endpoints functional
- Performance within SLOs

## Rollback Plan

If issues arise:
1. Set `BREAK_LEGACY_AUTH_IMPORTS=0` to restore legacy imports
2. Revert to previous auth.py implementation
3. Investigate and fix issues
4. Re-implement shim with fixes

## Contact

For questions about the migration:
- **Team**: Backend Team
- **Slack**: #backend-auth
- **Docs**: This file and inline code comments

## Related Files

- `app/api/auth.py` - Deprecation shim
- `app/auth/endpoints/*` - Canonical endpoints
- `app/metrics_deprecation.py` - Monitoring metrics
- `scripts/check_auth_shim.sh` - CI integrity check
- `tests/legacy/test_auth_shim.py` - Regression tests
