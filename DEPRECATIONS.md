# API Deprecations

This document tracks deprecated API endpoints and their planned removal timelines.

## Deprecation Policy

- **Deprecation Timeline**: Deprecated endpoints remain functional for **6 months** from the deprecation date
- **Warning Period**: Clients receive deprecation warnings in response headers and OpenAPI documentation
- **Breaking Changes**: Deprecated endpoints may be removed in **minor version updates** after the deprecation period
- **Migration Path**: Each deprecated endpoint includes migration instructions to the recommended replacement

## Currently Deprecated Endpoints

### Authentication & User Info

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /whoami` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/me` |
| `GET /me` (alias) | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/me` |

**Migration**: Use `/v1/me` for user information. This endpoint provides consistent authentication context.

### Integration Status Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /spotify/status` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/integrations/spotify/status` |
| `GET /google/status` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/integrations/google/status` |

**Migration**: Use the namespaced integration status endpoints under `/v1/integrations/{service}/status`.

### Home Assistant Compatibility

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /ha/entities` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/ha/entities` |
| `POST /ha/service` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/ha/service` |
| `GET /ha/resolve` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/ha/resolve` |

**Migration**: Add `/v1` prefix to all Home Assistant endpoints for consistency with the API versioning scheme.

### Calendar Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /list` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/list` |
| `GET /next` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/next` |
| `GET /today` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/today` |
| `GET /calendar/list` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/list` |
| `GET /calendar/next` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/next` |
| `GET /calendar/today` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/calendar/today` |

**Migration**: Use the versioned `/v1/calendar/*` endpoints instead of the root-level aliases.

### Device & Care Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /device_status` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/care/device_status` |
| `GET /care/device_status` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/care/device_status` |

**Migration**: Use the versioned `/v1/care/device_status` endpoint.

### Music Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /music` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/music` |
| `GET /music/devices` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/music/devices` |
| `PUT /music/device` | Deprecated | v3.0.0 | 2025-09-01 | `PUT /v1/music/device` |

**Migration**: Use the versioned `/v1/music/*` endpoints.

### Media Processing Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `POST /transcribe/{job_id}` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/transcribe/{job_id}` |
| `POST /tts/speak` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/tts/speak` |

**Migration**: Use the versioned `/v1/transcribe/*` and `/v1/tts/*` endpoints.

### Admin Endpoints

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `POST /admin/reload_env` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/admin/reload_env` |
| `POST /admin/self_review` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/admin/self_review` |
| `POST /admin/vector_store/bootstrap` | Deprecated | v3.0.0 | 2025-09-01 | `POST /v1/admin/vector_store/bootstrap` |

**Migration**: Use the versioned `/v1/admin/*` endpoints.

### OAuth Compatibility

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /google/oauth/callback` | Deprecated | v3.0.0 | 2025-09-01 | `GET /v1/google/oauth/callback` |

**Migration**: Use the versioned `/v1/google/oauth/callback` endpoint.

### Legacy Music HTTP Routes

| Deprecated Endpoint | Status | Deprecated Since | Removal Date | Replacement |
|---------------------|--------|------------------|--------------|-------------|
| `GET /state` | Deprecated | 2025-09-13 | 2026-03-13 | `GET /v1/music/state` |
| `GET /v1/legacy/state` | Deprecated | 2025-09-13 | 2026-03-13 | `GET /v1/music/state` |

**Migration**: Use the versioned `/v1/music/state` endpoint for music state information.

#### Legacy Route Implementation Notes

- **HTTP Status for Redirects**: Legacy routes use **307 Temporary Redirect** to preserve request method and body
- **Headers**: All legacy routes return RFC 8594 compliant deprecation headers:
  - `Deprecation: true`
  - `Sunset: <RFC3339 timestamp 90 days from now>`
  - `Link: </docs#legacy>; rel="deprecation"`
- **Metrics**: Usage tracked via `legacy_hits_total` Prometheus metric with endpoint labels
- **Kill Criteria**: Routes may be removed when `legacy_hits_total == 0` for 30 consecutive days
- **Feature Flag**: Controlled by `LEGACY_MUSIC_HTTP=1` environment variable

**See also**: [LEGACY_DEPRECATION_DECISIONS.md](LEGACY_DEPRECATION_DECISIONS.md) for detailed decision rationale and kill date planning.

## OpenAPI Documentation

All deprecated endpoints are marked with `deprecated: true` in the OpenAPI specification:

```yaml
paths:
  /whoami:
    get:
      deprecated: true
      description: "DEPRECATED: Use /v1/me instead"
```

## Client Migration Guide

### Python Clients

```python
# Before (deprecated)
response = requests.get("http://api.example.com/whoami")

# After (recommended)
response = requests.get("http://api.example.com/v1/me")
```

### JavaScript/TypeScript Clients

```typescript
// Before (deprecated)
const response = await fetch('/spotify/status');

// After (recommended)
const response = await fetch('/v1/integrations/spotify/status');
```

## Monitoring Deprecation Usage

Deprecated endpoints are tracked through:

1. **OpenAPI Warnings**: FastAPI logs warnings when deprecated endpoints are accessed
2. **Metrics**: Custom metrics track usage of deprecated endpoints
3. **Logs**: Structured logs include deprecation notices

## Removal Process

1. **Deprecation Notice**: Endpoints marked as deprecated with timeline
2. **Monitoring Period**: Track usage and client migration progress
3. **Graceful Shutdown**: Endpoints return 410 Gone after removal date
4. **Documentation Updates**: Update API documentation and client libraries

## Adding New Deprecations

When deprecating an endpoint:

1. Add `deprecated=True` parameter to the route decorator
2. Update this DEPRECATIONS.md file with:
   - Endpoint path and method
   - Deprecation date
   - Planned removal date (typically 6 months later)
   - Recommended replacement endpoint
   - Migration instructions
3. Update OpenAPI descriptions with deprecation notices
4. Notify API consumers through release notes

## Questions?

For questions about specific deprecations or migration assistance, please refer to:

- [API Documentation](docs/api.md)
- [Migration Guide](docs/migrations.md)
- [Release Notes](CHANGELOG.md)
