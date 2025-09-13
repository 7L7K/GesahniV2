# Domain: Google

## Current Purpose

The Google domain handles OAuth 2.0 authentication, token management, and integration with Google APIs for the GesahniV2 application. It provides:

- **OAuth 2.0 PKCE Flow** with proof-of-key-exchange challenge-response for secure authentication
- **Unified Token Management** with automatic refresh, storage in SQLite/Redis, and identity mapping
- **Google API Integration** for Gmail, Calendar, and user profile services
- **Background Token Refresh** with cron-based proactive renewal and error handling
- **State Parameter Security** with signed JWT state tokens for CSRF protection
- **Multi-tenant Identity Storage** with identity_id mapping for user data consistency
- **Error Handling and Recovery** with structured OAuth error responses and retry logic
- **Metrics and Observability** with comprehensive authentication event tracking
- **Scope-based Permissions** with granular access control for different Google services

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/v1/auth/google/login_url`** (GET) → `app.api.google_oauth.login_url()` - Generate OAuth authorization URL with PKCE
- **`/v1/auth/google/callback`** (GET) → `app.api.google_oauth.callback()` - Handle OAuth callback and token exchange
- **`/v1/integrations/google/status`** (GET) → `app.api.google.status()` - Check Google integration connection status
- **`/v1/google/services`** (GET) → `app.api.google_services.services()` - List available Google services
- **`/v1/google/gmail`** (GET) → `app.api.google.gmail()` - Access Gmail API endpoints
- **`/v1/google/calendar`** (GET) → `app.api.google.calendar()` - Access Calendar API endpoints

### OAuth Flow Handlers

- **Authorization URL Generation** → `app.integrations.google.oauth.get_authorization_url()` - Create Google OAuth URL with state/CSRF protection
- **Token Exchange** → `app.integrations.google.oauth.exchange_code_for_tokens()` - Trade authorization code for access/refresh tokens
- **Token Refresh** → `app.integrations.google.oauth.refresh_access_token()` - Refresh expired access tokens
- **State Validation** → `app.integrations.google.state.verify_signed_state()` - Validate OAuth callback state parameter

### Background Tasks

- **Token Refresh Cron** → `app.cron.google_refresh.main()` - Proactive token renewal for all users
- **Refresh Deduplication** → `app.integrations.google.refresh.refresh_dedup()` - Prevent concurrent refresh attempts
- **Token Health Monitoring** → `app.integrations.google.refresh.health_check()` - Monitor token validity and expiry

### Startup Tasks

- **Google Configuration** → `app.integrations.google.config.configure_google()` - Load OAuth client credentials and settings
- **Token Store Initialization** → `app.auth_store_tokens.TokenDAO` - Initialize SQLite token storage
- **Metrics Setup** → `app.metrics.google_metrics()` - Initialize Google-specific Prometheus metrics
- **Cron Job Registration** → Background task scheduler for token refresh cycles

## Internal Dependencies

### Core Google Modules
- **`app.integrations.google.oauth.GoogleOAuth`** - OAuth 2.0 implementation with PKCE support
- **`app.integrations.google.refresh.GoogleRefreshHelper`** - Token refresh coordination and deduplication
- **`app.integrations.google.state.GoogleStateManager`** - State parameter generation and validation
- **`app.integrations.google.http_exchange.GoogleHTTPExchange`** - HTTP client for token exchange operations
- **`app.integrations.google.errors.GoogleOAuthError`** - Structured error handling for OAuth failures

### Token Management
- **`app.auth_store_tokens.TokenDAO`** - SQLite-based token storage and retrieval
- **`app.models.third_party_tokens.ThirdPartyToken`** - Token data model with encryption support
- **`app.token_store`** - Redis-based distributed token storage for scaling
- **`app.integrations.google.db.GoogleTokenDB`** - Google-specific token database operations

### API Integration
- **`app.integrations.google.services.GoogleServices`** - Service discovery and API client management
- **`app.api.google_oauth`** - OAuth endpoints and callback handling
- **`app.api.google_services`** - Google API service endpoints (Gmail, Calendar)
- **`app.api.google`** - Legacy Google API endpoints and compatibility layer

### Authentication Integration
- **`app.deps.user.get_current_user_id()`** - User resolution with Google identity support
- **`app.auth_core.resolve_auth()`** - Unified authentication resolution including Google tokens
- **`app.session_store.SessionCookieStore`** - Session management with Google identity mapping
- **`app.metrics.google_metrics()`** - Google-specific authentication metrics

## External Dependencies

### Google APIs
- **Google OAuth 2.0** - User authentication and authorization
- **Google Identity Services** - User profile and email information
- **Gmail API** - Email access and management
- **Google Calendar API** - Calendar events and scheduling
- **Google People API** - User profile and contact information

### Storage Systems
- **SQLite** - Local token storage via `third_party_tokens.db`
- **Redis** - Distributed token storage for production deployments
- **File system** - Configuration files and temporary OAuth state storage

### Third-party Libraries
- **httpx** - Async HTTP client for Google API communication
- **google-auth** - Google authentication and credential management
- **google-api-python-client** - Google API client library
- **cryptography** - JWT token signing and verification
- **PyJWT** - JSON Web Token encoding/decoding

### Environment Configuration
- **GOOGLE_CLIENT_ID** - Google OAuth application client identifier
- **GOOGLE_CLIENT_SECRET** - Google OAuth application client secret
- **GOOGLE_REDIRECT_URI** - OAuth callback URL for token exchange
- **GOOGLE_SCOPES** - Requested OAuth scopes (profile, email, gmail, calendar)
- **JWT_STATE_SECRET** - Secret for signing OAuth state parameters

## Invariants / Assumptions

- **PKCE Security**: OAuth flow always uses PKCE with cryptographically secure verifier generation
- **State Parameter Security**: OAuth state parameter always signed with JWT for CSRF protection
- **Token Storage Identity**: Tokens stored with identity_id for consistent user mapping across services
- **Refresh Token Persistence**: Refresh tokens never expire and can be used indefinitely for renewal
- **Scope Validation**: Token scopes validated before API calls requiring specific permissions
- **Clock Synchronization**: System clock must be synchronized for token expiry validation
- **Client Credentials**: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured
- **Redirect URI Security**: GOOGLE_REDIRECT_URI must match registered OAuth application URI
- **Token Encryption**: Sensitive tokens encrypted at rest in database storage
- **Identity Consistency**: identity_id field provides stable user identification across token refreshes

## Known Weirdness / Bugs

- **PKCE State Storage**: PKCE challenges and state parameters not persisted across application restarts
- **Concurrent Refresh Race**: Multiple concurrent requests may trigger duplicate refresh attempts
- **Token Identity Mapping**: Legacy user_id field may become inconsistent during identity migrations
- **State Parameter Expiry**: Signed state parameters may expire before OAuth callback completion
- **API Rate Limit Handling**: Limited handling of Google API rate limits and backoff strategies
- **Error Response Consistency**: Different error formats across various OAuth failure scenarios
- **Token Scope Evolution**: Existing tokens may not include newly requested scopes
- **Clock Skew Sensitivity**: Token expiry validation sensitive to system clock drift
- **Session Identity Sync**: Session store may become desynchronized with token identity updates
- **Refresh Token Revocation**: No detection of refresh token revocation by user in Google account

## Observed Behavior

### OAuth Flow States

**Authorization Initiation:**
```python
# Generate signed state parameter for CSRF protection
state = generate_signed_state(user_id="user123", redirect_url="/dashboard")

# Create authorization URL with PKCE challenge
url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&scope={scopes}&state={state}&access_type=offline&include_granted_scopes=true&prompt=consent&code_challenge={challenge}&code_challenge_method=S256"
```

**Token Exchange:**
```python
# Exchange authorization code for tokens with PKCE verification
response = await httpx.post("https://oauth2.googleapis.com/token", data={
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": redirect_uri,
    "client_id": client_id,
    "client_secret": client_secret,
    "code_verifier": verifier  # PKCE verification
})

# Store tokens with identity mapping
token_data = ThirdPartyToken(
    user_id=user_id,
    identity_id=identity.sub,  # Google user ID as canonical identifier
    provider="google",
    access_token=access_token,
    refresh_token=refresh_token,
    expires_at=time.time() + expires_in,
    scope=scope
)
await upsert_token(token_data)
```

**Token Refresh:**
```python
# Refresh expired access token
response = await httpx.post("https://oauth2.googleapis.com/token", data={
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
    "client_id": client_id,
    "client_secret": client_secret
})

# Update stored token with new access token
await upsert_token(updated_token)
```

### API Integration Patterns

**Gmail API Access:**
```python
# Build Gmail service with refreshed credentials
credentials = Credentials(
    token=access_token,
    refresh_token=refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id,
    client_secret=client_secret
)

service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
messages = service.users().messages().list(userId="me", maxResults=10).execute()
```

**Calendar API Access:**
```python
# Build Calendar service
service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
events = service.events().list(calendarId="primary", maxResults=10).execute()
```

**User Profile Access:**
```python
# Get user profile information
profile = await httpx.get("https://www.googleapis.com/oauth2/v2/userinfo",
    headers={"Authorization": f"Bearer {access_token}"})
```

### Error Handling Patterns

**OAuth Errors:**
- **invalid_grant**: Authorization code expired or invalid → OAuth flow restart required
- **access_denied**: User denied authorization → Graceful failure with user notification
- **invalid_client**: Client credentials invalid → Configuration error
- **redirect_uri_mismatch**: Callback URL mismatch → Configuration validation required

**Token Errors:**
- **invalid_token**: Access token expired or invalid → Automatic refresh attempt
- **insufficient_scope**: Token lacks required permissions → Scope re-authorization needed
- **token_revoked**: Refresh token revoked by user → Re-authentication required

**API Errors:**
- **403 Forbidden**: Insufficient API permissions → Scope validation and re-authorization
- **404 Not Found**: Resource not found → User notification and graceful degradation
- **429 Too Many Requests**: Rate limited → Exponential backoff and retry logic
- **500 Internal Server Error**: Google API error → Circuit breaker activation

### Response Status Codes

- **200 OK**: Successful OAuth flow completion, API data retrieval
- **201 Created**: New token/resource created successfully
- **302 Found**: OAuth redirect to Google authorization page
- **400 Bad Request**: Invalid OAuth parameters, malformed requests
- **401 Unauthorized**: Invalid/expired tokens, authentication required
- **403 Forbidden**: Insufficient permissions, scope violations
- **404 Not Found**: Invalid callback URL, resource not found
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Token exchange failure, internal errors
- **502 Bad Gateway**: Google OAuth/API temporarily unavailable

### Token Lifecycle Management

**Token Creation:**
```json
{
  "id": "google:abc123def",
  "user_id": "user123",
  "identity_id": "google_user_456",
  "provider": "google",
  "access_token": "[REDACTED]",
  "refresh_token": "1/abc123def...",
  "scope": "openid profile email https://www.googleapis.com/auth/gmail.readonly",
  "expires_at": 1640995200,
  "created_at": 1640991600,
  "updated_at": 1640991600
}
```

**Token Refresh:**
```json
{
  "access_token": "[REDACTED]",
  "expires_in": 3600,
  "scope": "openid profile email https://www.googleapis.com/auth/gmail.readonly",
  "token_type": "Bearer"
}
```

**Token Validation:**
```python
# Check token expiry with clock skew tolerance
if time.time() > (expires_at - 60):  # 1 minute buffer
    await refresh_token()
```

### Circuit Breaker Behavior

- **Failure Threshold**: 3 consecutive OAuth/token failures trigger circuit breaker
- **Cooldown Period**: 300 seconds (5 minutes) before attempting recovery
- **Health Check**: Automatic health probes during open circuit state
- **Fallback Strategy**: Graceful degradation with cached data when available
- **Recovery Logic**: Single success resets failure counter and closes circuit

### Refresh Deduplication

**Concurrent Request Handling:**
```python
# First request initiates refresh
key = f"google:{user_id}"
if key not in _inflight:
    _inflight[key] = asyncio.Future()
    # Perform refresh
    result = await oauth.refresh_access_token(refresh_token)
    _inflight[key].set_result(result)
else:
    # Wait for existing refresh to complete
    result = await _inflight[key]

_inflight.pop(key, None)  # Cleanup
```

**Metrics Tracking:**
```python
# Track refresh success/failure
GOOGLE_REFRESH_SUCCESS.labels(user_id=user_id).inc()
GOOGLE_REFRESH_FAILED.labels(user_id=user_id, reason="invalid_grant").inc()
```

## TODOs / Redesign Ideas

### Immediate Issues
- **PKCE Persistence**: Store PKCE challenges and state parameters in Redis for restart resilience
- **Concurrent Refresh Coordination**: Implement distributed locks to prevent duplicate refresh attempts
- **Identity Migration**: Complete migration from user_id to identity_id for consistent token mapping
- **State Parameter TTL**: Implement configurable TTL for signed state parameters
- **Error Response Standardization**: Unify error response formats across OAuth failure scenarios

### Architecture Improvements
- **Token Encryption**: Implement proper encryption for stored refresh tokens
- **OAuth State Storage**: Move OAuth state from signed JWT to server-side storage
- **API Client Caching**: Implement intelligent API client caching with automatic refresh
- **Scope Evolution**: Add support for incremental scope requests without full re-authorization
- **Identity Provider Interface**: Abstract Google OAuth behind generic identity provider interface

### Security Enhancements
- **Token Binding**: Implement token binding to prevent token replay attacks
- **Device Authorization**: Add explicit device authorization flows for new devices
- **Scope Minimization**: Implement just-in-time scope requests based on operation
- **Audit Logging**: Add comprehensive audit logging for all Google API operations
- **Token Revocation Detection**: Detect and handle refresh token revocation by users

### Observability Improvements
- **OAuth Flow Metrics**: Add detailed metrics for OAuth completion rates and failure points
- **Token Health Dashboard**: Create dashboard for token expiry and refresh status
- **API Usage Analytics**: Track Google API usage patterns for cost optimization
- **Error Correlation**: Improve correlation between OAuth errors and application failures
- **Performance Profiling**: Add detailed timing metrics for OAuth flow stages

### Future Capabilities
- **Multi-Google Account Support**: Allow users to connect multiple Google accounts
- **Advanced API Integration**: Expand to Drive, Photos, and other Google services
- **Smart Token Management**: Implement predictive token refresh based on usage patterns
- **Federated Identity**: Support SAML/OIDC alongside OAuth for enterprise scenarios
- **Consent Management**: Build user-facing consent management for granted scopes
- **Cross-Platform Sync**: Synchronize Google data across multiple client platforms
- **Offline Mode**: Implement offline access patterns with local data caching
- **API Rate Optimization**: Implement intelligent request batching and caching
- **Service Health Monitoring**: Add proactive monitoring of Google service availability
- **Compliance Automation**: Implement automated token lifecycle management for compliance
