# Integrations: Adding New Providers

This guide shows how to add a new integration provider (like Apple Music, YouTube Music, etc.) following our established patterns.

## 🏗️ Architecture Overview

Our integration system uses a consistent pattern:
- **Factory Pattern**: `app/factories.py` - Pure functions for creating service instances
- **Dependency Injection**: `app/token_store_deps.py` - FastAPI dependencies for lifecycle management
- **Contract Testing**: `tests/contract/` - Ensures all providers behave consistently
- **Observability**: Metrics and structured logging for monitoring

## 📋 5 Steps to Add a New Provider

### Step 1: Define Status Response Contract

Create a status response model that matches the canonical contract:

```python
# app/api/{provider}.py
from enum import Enum

class ProviderStatusReason(str, Enum):
    no_tokens = "no_tokens"
    needs_reauth = "needs_reauth"
    expired_with_refresh = "expired_with_refresh"
    connected = "connected"
    # Add provider-specific reasons as needed

class ProviderStatusResponse(BaseModel):
    connected: bool
    reason: ProviderStatusReason
    details: Optional[dict] = None
    expires_at: Optional[int] = None
    last_refresh_at: Optional[int] = None
    refreshed: bool = False
    scopes: Optional[list[str]] = None
```

### Step 2: Implement Factory & Dependencies

Add your provider to the factory system:

```python
# app/factories.py
def make_provider_client() -> ProviderClient:
    """Factory for provider client instances."""
    return ProviderClient()

# app/token_store_deps.py - Already handles all providers generically
# No changes needed - uses make_token_store() which works for all providers
```

### Step 3: Create Provider API Module

Create `app/api/{provider}.py` with the standard endpoints:

```python
from fastapi import APIRouter, Depends, Request
from ..token_store_deps import get_token_store_dep

router = APIRouter(prefix="/{provider}")
integrations_router = APIRouter(prefix="/integrations/{provider}")

# Status endpoint
@integrations_router.get("/status")
async def integrations_provider_status(
    request: Request,
    store=Depends(get_token_store_dep)
):
    """Standard status endpoint for frontend polling."""
    return await provider_status(request, store)

# Disconnect endpoint
@integrations_router.post("/disconnect")
async def integrations_provider_disconnect(
    request: Request,
    store=Depends(get_token_store_dep)
):
    """Standard disconnect endpoint."""
    return await provider_disconnect(request, store)

# Main status function with metrics
async def provider_status(request: Request, store):
    try:
        current_user = await get_current_user_id(request=request)
    except Exception:
        PROVIDER_STATUS_REQUESTS_COUNT.labels(
            status="unauthorized", auth_state="failed"
        ).inc()
        return json_error("unauthorized", "Authentication required", 401)

    # Check token
    token = await store.get_token(current_user, "{provider}")
    if not token:
        PROVIDER_STATUS_REQUESTS_COUNT.labels(
            status="no_tokens", auth_state="ok"
        ).inc()
        return ProviderStatusResponse(
            connected=False,
            reason=ProviderStatusReason.no_tokens
        )

    # Check token validity, scopes, etc.
    # ... provider-specific logic ...

    # Success case
    PROVIDER_STATUS_REQUESTS_COUNT.labels(
        status="connected", auth_state="ok"
    ).inc()
    PROVIDER_STATUS_CONNECTED.labels(user=current_user).inc()

    return ProviderStatusResponse(
        connected=True,
        reason=ProviderStatusReason.connected,
        # ... other fields ...
    )

# Disconnect function
async def provider_disconnect(request: Request, store):
    current_user = await get_current_user_id(request=request)
    success = await store.mark_invalid(current_user, "{provider}")

    if success:
        PROVIDER_DISCONNECT_SUCCESS.labels(user_id=current_user).inc()

    return {"ok": success}
```

### Step 4: Add Metrics

Add provider-specific metrics to `app/metrics.py`:

```python
# Provider-specific metrics
PROVIDER_STATUS_REQUESTS_COUNT = Counter(
    "provider_status_requests_count",
    "Provider status API requests",
    ["status", "auth_state"],
)

PROVIDER_STATUS_CONNECTED = Counter(
    "provider_status_connected_total",
    "Provider status responses reporting connected",
    ["user"],
)

PROVIDER_DISCONNECT_SUCCESS = Counter(
    "provider_disconnect_success_total",
    "Provider disconnect success",
    ["user_id"],
)
```

### Step 5: Add Contract Tests

Extend `tests/contract/test_integration_status_contract.py`:

```python
# Add to CANONICAL_STATUS_REASONS if needed
# Add mapping for provider-specific reasons to canonical ones

def test_provider_status_reasons_contract(self, client):
    """Test that Provider status endpoint returns canonical reasons."""
    # Similar to Spotify/Google tests
    # Login, check status, verify canonical reasons

def test_provider_integration_status_consistency(self, client):
    """Test that Provider integration endpoint is consistent."""
    # Similar to existing consistency tests
```

## 🎯 Key Patterns to Follow

### ✅ Do This
- Use `Depends(get_token_store_dep)` for all endpoints
- Return canonical status reasons from `CANONICAL_STATUS_REASONS`
- Emit metrics for all status outcomes
- Handle authentication failures gracefully
- Follow the exact JSON response structure

### ❌ Don't Do This
- Don't create provider-specific dependency functions
- Don't invent new status reasons without adding to canonical set
- Don't skip metrics - they're critical for observability
- Don't handle auth differently from the established pattern

## 🔍 Testing Checklist

Before submitting your provider:

- [ ] All contract tests pass
- [ ] Metrics are emitted for all code paths
- [ ] Chaos tests handle token failures gracefully
- [ ] Status JSON matches established shape
- [ ] Disconnect endpoint works correctly
- [ ] Integration appears in router logs

## 📊 Monitoring

Once deployed, monitor:

```prometheus
# Status distribution
provider_status_requests_count{status="connected"}
provider_status_requests_count{status="no_tokens"}
provider_status_requests_count{status="needs_reauth"}

# Error rates
rate(provider_status_requests_count{status="unauthorized"}[5m])
```

## 🚀 Example: Adding Apple Music

1. Create `app/api/apple.py` following the pattern above
2. Add Apple metrics to `app/metrics.py`
3. Extend contract tests for Apple
4. Add Apple to router configuration
5. Test with chaos scenarios

The pattern ensures all providers work identically from the frontend's perspective!
