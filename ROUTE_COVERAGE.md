# Route Coverage Testing

This document describes the route coverage testing system that ensures every canonical API route has at least one test touching it.

## Overview

The route coverage system provides:

1. **Automatic route discovery** - Extracts all routes from the FastAPI application
2. **Coverage analysis** - Compares routes against test coverage markers
3. **CI integration** - Fails builds when routes are uncovered
4. **Smoke tests** - Minimal happy-path tests for core surface areas

## How It Works

### Route Discovery

The system automatically discovers all `/v1/*` routes from the FastAPI application by:
- Creating the app instance using `create_app()`
- Extracting routes from `app.routes`
- Filtering to include only v1 routes (excluding OPTIONS preflight)

### Coverage Markers

Tests can declare which routes they cover using coverage markers:

```python
def test_my_endpoint(client):
    """covers: GET: /v1/my/endpoint"""
    response = client.get('/v1/my/endpoint')
    assert response.status_code == 200
```

Or using pytest markers:

```python
@pytest.mark.covers("GET:/v1/my/endpoint")
def test_my_endpoint(client):
    response = client.get('/v1/my/endpoint')
    assert response.status_code == 200
```

### Coverage Analysis

The `RouteCoverageAnalyzer` class:
- Extracts all canonical routes from the application
- Scans test files for coverage markers
- Builds a coverage inventory mapping routes to covering tests
- Generates detailed coverage reports

## Usage

### Running Coverage Checks

```bash
# Check coverage (non-failing)
make route-coverage-check

# Check coverage and fail if incomplete
make route-coverage-fail

# Generate JSON coverage report
make route-coverage-json
```

### Running Smoke Tests

```bash
# Run all smoke tests
make smoke-tests

# Run smoke tests with verbose output
make smoke-tests-verbose
```

### CI Integration

```bash
# Run full CI check (coverage + smoke tests)
make ci-route-check

# Run full check including auth sanity
make ci-full-check
```

### Programmatic Usage

```python
from tests.smoke.test_route_coverage import RouteCoverageAnalyzer

analyzer = RouteCoverageAnalyzer()
report = analyzer.get_coverage_report()

print(f"Coverage: {report['coverage_percentage']:.1f}%")
print(f"Uncovered: {report['uncovered_routes']}")
```

## Core Surface Areas

The smoke test suite covers these core surface areas:

### Auth (`/v1/auth/*`)
- `GET /v1/auth/examples`
- `POST /v1/auth/login`
- `POST /v1/auth/register`
- `POST /v1/auth/logout`
- `POST /v1/auth/refresh`
- `POST /v1/auth/token`

### Google OAuth (`/v1/google/*`)
- `GET /v1/google/login_url`
- `GET /v1/google/callback`
- `POST /v1/google/callback`
- `GET /v1/google/google/oauth/callback`

### Music (`/v1/music/*`)
- `GET /v1/music/devices`
- `POST /v1/music/device`
- `POST /v1/music`

### Spotify (`/v1/spotify/*`)
- `GET /v1/spotify/status`
- `GET /v1/spotify/connect`
- `GET /v1/spotify/callback`
- `POST /v1/spotify/callback`
- `GET /v1/spotify/disconnect`
- `DELETE /v1/spotify/disconnect`
- `GET /v1/spotify/health`
- `GET /v1/spotify/debug`

### Status (`/v1/status/*`)
- `GET /v1/status`
- `GET /v1/status/budget`
- `GET /v1/status/features`
- `GET /v1/status/integrations`
- `GET /v1/status/vector_store`
- `GET /v1/status/rate_limit`
- `GET /v1/status/preflight`

### Admin (`/v1/admin/*`)
- `GET /v1/admin/ping`
- `GET /v1/admin/config`
- `GET /v1/admin/metrics`
- `GET /v1/admin/system/status`
- `GET /v1/admin/rbac/info`
- `GET /v1/admin/users/me`
- `GET /v1/admin/config-check`

## Test Categories

### Smoke Tests (`@pytest.mark.smoke`)
Minimal happy-path tests that verify endpoints exist and respond. These tests:
- Accept any HTTP status code (200, 401, 403, 404, 500, etc.)
- Focus on endpoint availability rather than functionality
- Run quickly and provide basic sanity checking

### Route Coverage Tests (`@pytest.mark.route_coverage`)
Tests that validate route coverage completeness:
- `test_route_coverage_completeness` - Fails if routes are uncovered
- `test_route_coverage_report` - Generates coverage reports

### Contract Tests (`@pytest.mark.contract`)
Tests that validate API contracts and behavior:
- Response schemas
- Error handling
- Authentication requirements

## CI Integration

### GitHub Actions

The `.github/workflows/route-coverage.yml` workflow:
- Runs on pushes and PRs to main/master/develop
- Checks route coverage completeness
- Runs smoke tests
- Generates coverage reports

### Local Development

```bash
# Quick check during development
python scripts/check_route_coverage.py --verbose

# Fail-fast check for CI
python scripts/check_route_coverage.py --fail-on-missing
```

## Adding Coverage for New Routes

When adding new routes:

1. **Add the route** to your FastAPI router
2. **Add a test** with appropriate coverage markers
3. **Run coverage check** to verify: `make route-coverage-check`
4. **Add smoke test** if it's a core surface area endpoint

Example:

```python
# In your router
@router.get("/v1/my/new/endpoint")
async def my_new_endpoint():
    return {"message": "Hello World"}

# In your test file
def test_my_new_endpoint(client):
    """covers: GET: /v1/my/new/endpoint"""
    response = client.get('/v1/my/new/endpoint')
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
```

## Coverage Reports

### Console Output
```
=== ROUTE COVERAGE REPORT ===
Total routes: 85
Covered routes: 72
Uncovered routes: 13
Coverage: 84.7%

Uncovered routes:
  GET: /v1/some/endpoint
  POST: /v1/another/endpoint
  ...
```

### JSON Output
```json
{
  "total_routes": 85,
  "covered_routes": 72,
  "uncovered_routes": 13,
  "coverage_percentage": 84.7,
  "uncovered": [["GET", "/v1/some/endpoint"], ...],
  "covered": [["GET", "/v1/covered/endpoint"], ...]
}
```

## Troubleshooting

### Common Issues

1. **Route not detected**: Ensure the route is properly registered in the FastAPI app
2. **Coverage marker not recognized**: Check marker format (`METHOD: /path`)
3. **Test not running**: Ensure test is in `tests/` directory and follows naming conventions

### Debug Commands

```bash
# List all routes
python -c "from app.main import create_app; app = create_app(); [print(f'{list(r.methods)}: {r.path}') for r in app.routes if hasattr(r, 'methods') and r.path.startswith('/v1/')]"

# Check test discovery
pytest --collect-only tests/smoke/

# Debug coverage analysis
python scripts/check_route_coverage.py --verbose
```

## Configuration

### Pytest Configuration (`pytest.ini`)

```ini
[tool:pytest]
markers =
    smoke: Golden-flow smoke tests for core surface areas
    covers: mark test as covering specific routes (format: method:path)
    route_coverage: tests that validate route coverage completeness
```

### Environment Variables

- `ROUTE_COVERAGE_MINIMUM`: Minimum coverage percentage required (default: 100%)
- `ROUTE_COVERAGE_STRICT`: Fail on any uncovered routes (default: true)

## Best Practices

1. **Always add coverage markers** to new tests
2. **Use descriptive test names** that indicate what they cover
3. **Run coverage checks** before committing
4. **Keep smoke tests minimal** - focus on endpoint existence
5. **Update coverage** when routes change

## Future Enhancements

- Integration with coverage.py for code coverage
- Automatic test generation for uncovered routes
- Coverage trending and history
- Route deprecation warnings
- Performance benchmarking for routes
