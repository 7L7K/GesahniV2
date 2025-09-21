# OpenAPI Contract Snapshots

This directory contains frozen snapshots of the OpenAPI schema for different environments.
These snapshots serve as contracts that ensure API changes are intentional and tracked.

## Files

- **`openapi.ci.json`**: Minimal API surface for CI/testing (no optional integrations)
- **`openapi.dev.min.json`**: Development environment baseline (no optional integrations)
- **`openapi.prod.min.json`**: Production environment baseline (no optional integrations)
- **`openapi.dev.spotify.json`**: Development with Spotify integration enabled

## Usage

### Running Contract Tests

```bash
# Run all contract tests
python -m pytest tests/contract/ -v

# Run specific environment test
python -m pytest tests/contract/test_openapi_contract.py::test_ci_schema_paths_match_snapshot -v
```

### Updating Contracts

When you intentionally change the API surface (add/remove routes), update the snapshots:

```bash
# Generate new contract snapshots
python generate_contracts.py

# Commit the updated snapshot files with your API changes
git add contracts/
git commit -m "feat: add new API endpoint /v1/example

- Add new endpoint for example functionality
- Update contract snapshots"
```

### What Gets Tested

The contract tests verify:
- ✅ Exact path matching between current schema and snapshot
- ✅ Environment-specific routing behavior
- ✅ No accidental route additions/removals
- ✅ Integration enablement works correctly

## Environment Behavior

### CI Mode (`CI=1`)
- Minimal surface: core routes only
- No optional integrations (Spotify, Apple, Device)
- Rate limiting disabled
- Fastest possible test execution

### Dev Mode (Default)
- Core routes + optional integrations when enabled
- `GSNH_ENABLE_SPOTIFY=1` adds Spotify routes
- `APPLE_OAUTH_ENABLED=1` adds Apple routes
- `DEVICE_AUTH_ENABLED=1` adds device routes

### Prod Mode (`ENV=prod`)
- Same as dev but with production middleware configuration
- Optional integrations available when enabled

## Adding New Contract Tests

If you add a new environment or integration, add corresponding contract tests:

```python
def test_new_environment_schema_paths_match_snapshot(monkeypatch):
    monkeypatch.setenv("NEW_ENV_VAR", "value")
    # ... test implementation
```

And generate the corresponding snapshot file in `generate_contracts.py`.

## Troubleshooting

### Test Failures

If contract tests fail:
1. Check if you intentionally changed the API
2. If yes: update snapshots with `python generate_contracts.py`
3. If no: investigate what caused the unexpected change

### Missing Snapshots

If snapshot files are missing:
```bash
python generate_contracts.py
```

### Environment Issues

If tests fail due to environment variables:
- Clear conflicting env vars: `unset CI GSNH_ENABLE_SPOTIFY GSNH_ENABLE_MUSIC APPLE_OAUTH_ENABLED DEVICE_AUTH_ENABLED`
- Run tests in isolation: `python -m pytest tests/contract/ -v`
