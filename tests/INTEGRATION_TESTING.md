# Integration Testing Guide

This guide covers best practices for testing FastAPI endpoints that use dependency injection, with a focus on token store operations.

## Core Principles

1. **Use Dependency Injection**: Never monkey patch module functions. Always override FastAPI dependencies.
2. **Test Through the Real Interface**: Use the same patterns your application uses in production.
3. **Verify Side Effects**: Assert on what your fake implementations record.
4. **Type Safety**: Use protocols to catch drift between real and fake implementations.

## Quick Start

### Basic Token Store Testing

```python
from tests.helpers.fakes import FakeTokenStore
from tests.helpers.overrides import override_token_store
from app.types.token_store import TokenStore

def test_spotify_callback():
    fake_store = FakeTokenStore()

    # Preload existing token if needed
    existing_token = ThirdPartyToken(user_id="u_123", provider="spotify", ...)
    preloaded = {(existing_token.user_id, existing_token.provider): existing_token}
    fake_store = FakeTokenStore(preloaded_tokens=preloaded)

    with override_token_store(fake_store):
        # Make your API calls
        response = client.get("/v1/spotify/callback?...")

        # Assert on response
        assert response.status_code == 302

        # Assert on side effects
        assert len(fake_store.newly_saved) == 1
        saved_token = fake_store.newly_saved[0]
        assert saved_token.access_token == "expected_token"
```

### Testing Existing Token Scenarios

```python
def test_callback_with_existing_token():
    # Preload a token that already exists
    existing_token = ThirdPartyToken(user_id="u_123", provider="spotify", ...)
    fake_store = FakeTokenStore(preloaded_tokens={
        (existing_token.user_id, existing_token.provider): existing_token
    })

    with override_token_store(fake_store):
        # Test token update scenario
        response = client.get("/v1/spotify/callback?code=new_code...")

        # Verify the token was updated
        assert len(fake_store.all_saved) == 2  # preloaded + updated
        assert len(fake_store.newly_saved) == 1  # only the update
```

## Available Helpers

### FakeTokenStore

```python
fake_store = FakeTokenStore(preloaded_tokens={...})

# Properties for assertions
fake_store.newly_saved  # Only tokens saved during test
fake_store.all_saved    # All tokens (including preloaded)
fake_store.tokens       # Current token map
```

### Override Helpers

```python
# Simple context manager
with override_token_store(fake_store):
    # Test code

# Generic dependency override
from tests.helpers.overrides import override_dependency
with override_dependency(get_token_store_dep, fake_store):
    # Test code
```

### Type Safety

```python
from app.types.token_store import TokenStore

# Runtime type checking
assert isinstance(fake_store, TokenStore)

# MyPy will catch interface mismatches at static analysis time
def test_with_type_checking(store: TokenStore):
    pass
```

## Testing Patterns

### Happy Path Testing

```python
def test_successful_token_flow():
    fake_store = FakeTokenStore()

    with override_token_store(fake_store):
        response = client.get("/v1/spotify/callback?code=abc&state=xyz")

        # Verify HTTP behavior
        assert response.status_code == 302
        assert "settings?spotify=connected" in response.headers["Location"]

        # Verify data behavior
        assert len(fake_store.newly_saved) == 1
        token = fake_store.newly_saved[0]
        assert token.provider == "spotify"
        assert token.user_id == "expected_user"
```

### Error Path Testing

```python
def test_token_save_failure():
    # Create a fake store that can simulate failures
    class FailingFakeStore(FakeTokenStore):
        async def upsert_token(self, token):
            return False  # Simulate failure

    fake_store = FailingFakeStore()

    with override_token_store(fake_store):
        response = client.get("/v1/spotify/callback?code=abc&state=xyz")

        # Should redirect with error
        assert response.status_code == 302
        assert "error=token_save_failed" in response.headers["Location"]
```

### Multi-Provider Testing

```python
def test_multiple_providers():
    fake_store = FakeTokenStore()

    # Add tokens for multiple providers
    spotify_token = ThirdPartyToken(user_id="u_123", provider="spotify", ...)
    google_token = ThirdPartyToken(user_id="u_123", provider="google", ...)

    preloaded = {
        (spotify_token.user_id, spotify_token.provider): spotify_token,
        (google_token.user_id, google_token.provider): google_token,
    }
    fake_store = FakeTokenStore(preloaded_tokens=preloaded)

    with override_token_store(fake_store):
        # Test operations work across providers
        has_spotify = await fake_store.has_any("u_123", "spotify")
        has_google = await fake_store.has_any("u_123", "google")
        has_any = await fake_store.has_any("u_123")

        assert has_spotify and has_google and has_any
```

## Advanced Patterns

### Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(
    user_id=st.text(min_size=1),
    provider=st.sampled_from(["spotify", "google"]),
    access_token=st.text(min_size=1)
)
async def test_token_roundtrip(user_id, provider, access_token):
    fake_store = FakeTokenStore()
    token = ThirdPartyToken(user_id=user_id, provider=provider, access_token=access_token, ...)

    await fake_store.upsert_token(token)
    retrieved = await fake_store.get_token(user_id, provider)

    assert retrieved.access_token == access_token
```

### State Machine Testing

```python
from hypothesis.stateful import RuleBasedStateMachine, rule

class TokenStoreMachine(RuleBasedStateMachine):
    def __init__(self):
        self.fake_store = FakeTokenStore()
        self.model_tokens = {}

    @rule(user=st.text(), provider=st.text(), token=st.builds(ThirdPartyToken))
    def upsert_token(self, user, provider, token):
        self.model_tokens[(user, provider)] = token
        # Test consistency between model and fake store
```

## Common Mistakes to Avoid

### ❌ Wrong: Monkey Patching

```python
# DON'T DO THIS
monkeypatch.setattr("app.api.spotify.upsert_token", fake_upsert)
```

### ❌ Wrong: Testing Implementation Details

```python
# DON'T DO THIS - tests internal database calls
assert mock_database_call.called_with(expected_params)
```

### ❌ Wrong: No Type Safety

```python
# DON'T DO THIS - no type checking
fake_store = SomeClass()  # Could drift from real interface
```

### ✅ Right: Dependency Injection + Side Effect Testing

```python
# DO THIS
fake_store = FakeTokenStore()
with override_token_store(fake_store):
    response = client.post("/api/endpoint")
    assert len(fake_store.newly_saved) == 1
```

## Running Tests

### Basic Test Execution

```bash
# Run all integration tests
pytest tests/features/ -v

# Run contract tests
pytest tests/contract/ -v

# Run property-based tests
pytest tests/contract/test_token_store_hypothesis.py -v

# Run with hypothesis statistics
pytest tests/contract/test_token_store_hypothesis.py --hypothesis-show-statistics
```

### CI Guardrails

```bash
# Check for legacy patches
./scripts/ci-guardrails.sh

# Or manually check
grep -r "app\.api\.spotify\.(upsert_token|get_token)" tests/
```

## Coverage Goals

- **Contract Tests**: 100% coverage of TokenStore implementations
- **Integration Tests**: All token store operations tested
- **Property Tests**: Edge cases covered via fuzzing

## Debugging Tips

### Inspecting Token State

```python
# See all saved tokens
print(fake_store.all_saved)

# See only newly saved tokens
print(fake_store.newly_saved)

# Check current token map
print(fake_store.tokens)
```

### Understanding Failures

- **No tokens saved**: Check that your endpoint actually calls upsert_token
- **Wrong token data**: Verify your test data matches what the endpoint expects
- **Type errors**: Ensure you're using ThirdPartyToken objects, not plain dicts

## Migration Guide

### From Monkey Patches to DI

**Before:**
```python
monkeypatch.setattr("app.api.spotify.upsert_token", lambda t: None)
```

**After:**
```python
fake_store = FakeTokenStore()
with override_token_store(fake_store):
    # Test code
    assert len(fake_store.newly_saved) == 1
```

### From Direct Database Testing to Contract Testing

**Before:**
```python
# Test direct database calls
assert database.insert_called_with(token_data)
```

**After:**
```python
# Test through contract
await real_store.upsert_token(token)
await fake_store.upsert_token(token)

real_result = await real_store.get_token(user, provider)
fake_result = await fake_store.get_token(user, provider)
assert real_result.user_id == fake_result.user_id
```

This approach ensures your tests are maintainable, type-safe, and catch regressions early while remaining focused on behavior rather than implementation details.
