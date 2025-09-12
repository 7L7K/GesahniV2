# API Routing Contract Matrix

This document provides a comprehensive overview of the GesahniV2 API routing contract, documenting all endpoints, their HTTP methods, authentication requirements, and expected response codes.

## Overview

The GesahniV2 API follows a versioned routing structure with `/v1/` prefix for stable endpoints. Authentication is primarily handled via JWT tokens (bearer auth or cookies) with OAuth integrations for third-party services.

### Router Architecture

The API uses a modular router system with the following core components:

- **Router Registry**: Central configuration in `app/routers/config.py`
- **Authentication Protection**: Decorators for route protection (`@public_route`, `@protected_route`, `@auth_only_route`)
- **OAuth Integrations**: Google, Spotify, Apple OAuth flows with PKCE protection
- **CSRF Protection**: Double-submit cookie pattern for state-changing operations
- **Rate Limiting**: IP and user-based rate limits on authentication endpoints

## Authentication Methods

- **Bearer Token**: `Authorization: Bearer <jwt>` - JWT tokens in request headers
- **Cookie Auth**: HttpOnly cookies (`access_token`, `refresh_token`, `session_id`) for session management
- **OAuth**: Google, Spotify, Apple OAuth flows with PKCE protection and state validation
- **PATs**: Personal Access Tokens with scoped permissions (admin, user, care scopes)
- **Dev Bypass**: Environment-based authentication bypass for local development (`AUTH_DEV_BYPASS=1`)
- **Multi-Source**: Priority order: Cookie → Header → Clerk → PAT fallback

## Response Code Patterns

- **200**: Success
- **201**: Created
- **204**: No Content (success)
- **303**: Redirect
- **400**: Bad Request
- **401**: Unauthorized
- **403**: Forbidden
- **404**: Not Found
- **405**: Method Not Allowed
- **429**: Too Many Requests
- **500**: Internal Server Error

## Core Endpoints

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/` | GET | None | 303 | Root redirect to docs |
| `/api` | GET | None | 200 | API information endpoint |
| `/docs` | GET | None | 200 | FastAPI documentation |
| `/redoc` | GET | None | 200 | ReDoc documentation |
| `/openapi.json` | GET | None | 200 | OpenAPI schema |
| `/album_art/*` | GET | None | 200, 404 | Static album art files |
| `/shared_photos/*` | GET | None | 200, 404 | Static shared photo files |

## Health & Monitoring

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/healthz` | GET | None | 200 | Liveness probe |
| `/v1/healthz` | GET | None | 200 | Versioned liveness probe |
| `/healthz/live` | GET | None | 200 | Process liveness check |
| `/healthz/ready` | GET | None | 200 | Readiness with component status |
| `/v1/health` | GET | None | 200 | Combined health status |
| `/healthz/deps` | GET | None | 200 | Optional dependencies health |
| `/v1/ping` | GET | None | 200 | Vendor health check |
| `/v1/vendor-health` | GET | None | 200 | All vendor health status |
| `/health/vector_store` | GET | None | 200 | Vector store diagnostics |
| `/v1/health/vector_store` | GET | None | 200 | Versioned vector store health |
| `/v1/health/qdrant` | GET | None | 200 | Qdrant health status |
| `/v1/health/chroma` | GET | None | 200 | Chroma health status |

## Authentication & Authorization

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/auth/whoami` | GET | Optional | 200, 401 | Current user identity |
| `/v1/auth/login` | POST | None | 200, 400, 401, 429 | User login |
| `/v1/auth/register` | POST | None | 200, 400, 409 | User registration |
| `/v1/auth/logout` | POST | Required | 204, 401 | Session logout |
| `/v1/auth/logout_all` | POST | Required | 204, 401 | Logout all sessions |
| `/v1/auth/refresh` | POST | Required | 200, 401, 429 | Token refresh |
| `/v1/auth/csrf` | GET | Optional | 200 | CSRF token issuer |
| `/v1/auth/pats` | GET, POST | Required | 200, 401, 403 | Personal access tokens |
| `/v1/auth/pats/{id}` | DELETE | Required | 204, 401, 403 | Revoke PAT |
| `/v1/auth/token` | POST | None | 200, 400, 403 | Dev token endpoint |
| `/v1/auth/examples` | GET | None | 200 | JWT examples |
| `/v1/auth/finish` | GET, POST | None | 200, 400 | OAuth finish endpoint |
| `/v1/auth/clerk/finish` | GET, POST | None | 200 | Clerk OAuth finish |

## OAuth Integrations

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/auth/google/login_url` | GET | None | 200, 404, 503 | Google OAuth URL generator with PKCE |
| `/v1/auth/google/callback` | GET, POST | None | 303, 400, 401, 403, 404, 409, 500 | Google OAuth callback with state validation |
| `/v1/auth/google/status` | GET | None | 200, 404 | Google OAuth integration status |
| `/v1/auth/spotify/login_url` | GET | None | 200, 404, 503 | Spotify OAuth URL generator with PKCE |
| `/v1/auth/spotify/callback` | GET, POST | None | 303, 400, 401, 403, 404, 409, 500 | Spotify OAuth callback with state validation |
| `/v1/auth/spotify/status` | GET | None | 200, 404 | Spotify OAuth integration status |
| `/v1/auth/apple/login_url` | GET | None | 200, 404, 503 | Apple OAuth URL generator with PKCE |
| `/v1/auth/apple/callback` | GET, POST | None | 303, 400, 401, 403, 404, 409, 500 | Apple OAuth callback with state validation |
| `/google/oauth/callback` | GET, POST | None | 303, 400, 500 | Legacy Google OAuth callback (compatibility) |

## Admin & Management

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/admin/ping` | GET | Admin scope | 200, 401, 403 | Admin connectivity check |
| `/v1/admin/users/me` | GET | User scope | 200, 401, 403 | Current admin user info |
| `/v1/admin/system/status` | GET | Admin scope | 200, 401, 403 | System status |
| `/v1/admin/tokens/google` | GET | Admin scope | 200, 401, 403 | Google token management |
| `/v1/admin/users/{id}/identities` | GET | Admin scope | 200, 401, 403 | User identity management |
| `/v1/admin/users/{id}/identities/{id}/unlink` | POST | Admin scope | 200, 401, 403 | Unlink user identity |
| `/v1/admin/surface/index` | GET | Admin scope | 200, 401, 403 | Surface index |
| `/v1/admin/metrics` | GET | Admin scope | 200, 401, 403 | System metrics |
| `/v1/admin/router/decisions` | GET | Admin scope | 200, 401, 403 | Router decision logs |
| `/v1/admin/retrieval/last` | GET | Admin scope | 200, 401, 403 | Last retrieval info |
| `/v1/admin/decisions/explain` | GET | Admin scope | 200, 401, 403 | Decision explanations |
| `/v1/admin/config` | GET, POST | Admin scope | 200, 401, 403 | Configuration management |
| `/v1/admin/config/test` | POST | Admin scope | 200, 401, 403 | Test configuration |
| `/v1/admin/errors` | GET | Admin scope | 200, 401, 403 | Error logs |
| `/v1/admin/self_review` | GET, POST | Admin scope | 200, 401, 403 | Self-review system |
| `/v1/admin/vector_store/stats` | GET | Admin scope | 200, 401, 403 | Vector store statistics |
| `/v1/admin/token_store/stats` | GET | Admin scope | 200, 401, 403 | Token store statistics |
| `/v1/admin/qdrant/collections` | GET | Admin scope | 200, 401, 403 | Qdrant collections |
| `/v1/admin/health/router_retrieval` | GET | Admin scope | 200, 401, 403 | Router retrieval health |
| `/v1/admin/flags` | GET | Admin scope | 200, 401, 403 | Feature flags |

## Core API Features

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/ask` | POST | Required | 200, 401, 429, 500 | Main AI query endpoint (OpenAI/LLaMA) |
| `/v1/transcribe` | POST | Required | 200, 401, 400, 413 | Audio transcription service |
| `/v1/tts` | POST | Required | 200, 401, 400 | Text-to-speech synthesis |
| `/v1/memories` | GET, POST | Required | 200, 401, 403 | User memory management |
| `/v1/memories/ingest` | POST | Required | 200, 401, 400 | Memory ingestion from documents |
| `/v1/care` | POST | Required | 200, 401, 400 | Care system alerts and sessions |
| `/v1/care/sessions` | GET | Required | 200, 401 | Active care sessions |
| `/v1/care/alerts` | GET, POST | Required | 200, 401, 403 | Care system alerts |
| `/v1/care/devices` | GET, POST | Required | 200, 401, 403 | Care device management |
| `/v1/calendar` | GET | Required | 200, 401 | Google Calendar integration |
| `/v1/calendar/next` | GET | Required | 200, 401 | Next calendar event |
| `/v1/google` | GET, POST | Required | 200, 401, 403 | Google services integration |
| `/v1/google/photos` | GET | Required | 200, 401, 403 | Google Photos access |
| `/v1/google/services` | GET | Required | 200, 401, 403 | Google service status |
| `/v1/devices` | GET, POST | Required | 200, 401, 403 | Device management |
| `/v1/ha` | POST | Required | 200, 401, 400 | Home Assistant command execution |
| `/v1/ha/states` | GET | Required | 200, 401 | Home Assistant state queries |
| `/v1/me` | GET | Required | 200, 401 | User profile information |
| `/v1/profile` | GET, POST | Required | 200, 401, 403 | User profile management |
| `/v1/schema` | GET | None | 200 | API schema information |

## Music Features

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/music` | GET, POST, PUT | Required | 200, 401, 400 | Music control |
| `/v1/music/state` | GET | Required | 200, 401 | Music player state |
| `/v1/music/queue` | GET | Required | 200, 401 | Music queue |
| `/v1/music/recommendations` | GET | Required | 200, 401 | Music recommendations |
| `/v1/music/devices` | GET | Required | 200, 401 | Available music devices |
| `/v1/music/device` | POST | Required | 200, 401, 400 | Set active device |
| `/v1/music/device` | PUT | Required | 200, 401, 400 | Update device settings |
| `/v1/music/restore_volume` | POST | Required | 200, 401 | Restore volume |
| `/v1/music/vibe` | POST | Required | 200, 401, 400 | Music vibe control |

## WebSocket Endpoints

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/ws` | WebSocket | Required | 101, 401, 403 | Main WebSocket connection (HTTP upgrade) |
| `/v1/ws/music` | WebSocket | Required | 101, 401, 403 | Music control WebSocket |
| `/v1/ws/care` | WebSocket | Required | 101, 401, 403 | Care system WebSocket |
| `/v1/ws/sessions` | WebSocket | Required | 101, 401, 403 | Session management WebSocket |

## Utility & Debug Endpoints

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/v1/csrf` | GET | Optional | 200 | CSRF token issuer |
| `/v1/util/csrf` | GET, POST | Optional | 200 | CSRF token management |
| `/v1/metrics` | GET | None | 200 | Prometheus metrics endpoint |
| `/v1/metrics/root` | GET | None | 200 | Root metrics endpoint |
| `/v1/status` | GET | None | 200 | Public status information |
| `/v1/status/plus` | GET | None | 200 | Extended status information |
| `/v1/config` | GET, POST | Admin scope | 200, 401, 403 | Configuration management |
| `/v1/config/check` | POST | Admin scope | 200, 401, 403 | Configuration validation |
| `/v1/debug/*` | Various | Varies | Varies | Debug endpoints (dev only) |
| `/v1/dev/*` | Various | None | Varies | Development endpoints (dev only) |
| `/__diag/*` | Various | None | 200 | Startup diagnostics (dev only) |

## Legacy Compatibility Routes

| Endpoint | Methods | Auth Requirements | Expected Codes | Description |
|----------|---------|-------------------|----------------|-------------|
| `/whoami` | GET | Optional | 200, 401 | Legacy whoami (redirects) |
| `/health` | GET | None | 200 | Legacy health (redirects) |
| `/healthz` | GET | None | 200 | Legacy healthz (redirects) |
| `/admin/{path}` | GET | Varies | Varies | Legacy admin (redirects) |
| `/csrf` | GET | Optional | 200 | Legacy CSRF (redirects) |
| `/login` | POST | None | 200, 400, 401 | Legacy login (redirects) |
| `/logout` | POST | Required | 204 | Legacy logout (redirects) |
| `/register` | POST | None | 200, 400 | Legacy register (redirects) |
| `/refresh` | POST | Required | 200 | Legacy refresh (redirects) |
| `/ask` | POST | Required | 200 | Legacy ask (redirects) |
| `/spotify/status` | GET | None | 200 | Legacy Spotify status (redirects) |
| `/google/status` | GET | None | 200 | Legacy Google status (redirects) |
| `/status` | GET | None | 200 | Legacy status (redirects) |

## Error Response Schema

All endpoints follow consistent error response patterns:

```json
{
  "code": "error.code",
  "detail": "Human readable message",
  "request_id": "uuid",
  "timestamp": "ISO8601"
}
```

## Authentication Response Schema

```json
{
  "is_authenticated": true,
  "session_ready": true,
  "user": {
    "id": "user_id",
    "email": "user@example.com"
  },
  "source": "cookie|header|clerk",
  "version": 1
}
```

## Router Configuration

The API uses a centralized router registry system defined in `app/routers/config.py` with the following key specifications:

- **Core Routers**: Always included (`app.api.auth`, `app.api.health`, etc.)
- **Optional Routers**: Enabled via environment variables (`SPOTIFY_ENABLED`, `APPLE_OAUTH_ENABLED`, etc.)
- **Conditional Routers**: Only included in specific environments (dev-only routers)
- **Router Prefixes**: Versioned paths (`/v1/`) for stable endpoints, legacy paths for compatibility

## Authentication Patterns

- **Multi-Source Auth**: Cookie → Header → Clerk → PAT priority order
- **Session Management**: JWT tokens with JTI tracking for refresh token rotation
- **Rate Limiting**: IP-based (5/min login, 30/hr) and user-based (10/hr login)
- **CSRF Protection**: Double-submit cookie pattern with configurable enforcement
- **OAuth Security**: PKCE protection, state validation, nonce consumption
- **Admin Scopes**: Granular permissions (`admin:read`, `admin:write`, `user:profile`)

## Error Handling

- **Structured Errors**: Consistent error response format with `code`, `detail`, `request_id`
- **HTTP Status Mapping**: 401 for auth failures, 403 for permission denied, 429 for rate limits
- **Logging**: Comprehensive audit logging for security events and authentication flows
- **Monitoring**: Prometheus metrics for auth success/failure rates

## Development Features

- **Dev Bypass**: `AUTH_DEV_BYPASS=1` for local development authentication
- **Debug Endpoints**: Extensive debugging tools under `/v1/debug/` and `/__diag/`
- **Test Compatibility**: Special handling for test environments and mock authentication
- **Startup Diagnostics**: Comprehensive router and middleware validation

## Notes

- **Router Registration**: All routers are registered dynamically via `register_routers(app)` function
- **Middleware Order**: Critical for security - CORS before CSRF, auth validation at appropriate layers
- **Static Files**: Album art and shared photos served via FastAPI StaticFiles mounting
- **Health Checks**: Readiness probes return 200 regardless of component status (status in response body)
- **WebSocket Upgrade**: HTTP 101 status code for successful WebSocket handshakes
- **OAuth Callbacks**: 303 See Other redirects for successful auth flows to prevent form resubmission

This matrix represents the current API contract as documented in the router configuration. New endpoints should follow these established patterns and be documented here.
