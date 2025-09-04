# Domain: Spotify

## Current Purpose

The Spotify domain handles OAuth authentication, Web API integration, and music playback control for the GesahniV2 application. It provides:

- **OAuth 2.0 with PKCE** flow for secure Spotify account linking with proof-of-key-exchange challenge-response
- **Unified token management** with automatic refresh, storage in SQLite, and Redis fallback
- **Web API client** with rate limiting, circuit breaker protection, and budget-aware timeouts
- **Music playback control** through Spotify Connect devices with play/pause/skip/seek functionality
- **Device discovery and management** with active device enumeration and transfer capabilities
- **Playlist and library access** with search, creation, and modification operations
- **Background token refresh** with cron-based proactive renewal and error handling
- **Scope-based permissions** with granular access control for user data and playback features
- **Integration with Home Assistant** through music skills and device control
- **Real-time status monitoring** with connection health checks and error reporting

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/v1/spotify/auth/login`** (GET) → `app.api.spotify.spotify_login()` - Initiate OAuth flow with PKCE
- **`/v1/spotify/auth/callback`** (GET) → `app.api.spotify.spotify_callback()` - Handle OAuth callback and token exchange
- **`/v1/integrations/spotify/status`** (GET) → `app.api.spotify.integrations_spotify_status()` - Check connection status
- **`/v1/music/play`** (POST) → `app.api.music.play()` - Start playback with entity/utterance resolution
- **`/v1/music/pause`** (POST) → `app.api.music.pause()` - Pause current playback
- **`/v1/music/resume`** (POST) → `app.api.music.resume()` - Resume paused playback
- **`/v1/music/next`** (POST) → `app.api.music.next()` - Skip to next track
- **`/v1/music/previous`** (POST) → `app.api.music.previous()` - Skip to previous track
- **`/v1/music/devices`** (GET) → `app.api.music.devices()` - List available Spotify devices
- **`/v1/music/state`** (GET) → `app.api.music.state()` - Get current playback state
- **`/v1/music/volume`** (POST) → `app.api.music.volume()` - Adjust playback volume
- **`/v1/music/seek`** (POST) → `app.api.music.seek()` - Seek to position in track

### OAuth Flow Handlers

- **PKCE Challenge Generation** → `app.integrations.spotify.oauth.generate_pkce()` - Create cryptographically secure verifier/challenge
- **Authorization URL Creation** → `app.integrations.spotify.oauth.make_authorize_url()` - Build Spotify OAuth URL with PKCE
- **Token Exchange** → `app.integrations.spotify.oauth.exchange_code()` - Trade authorization code for access/refresh tokens
- **State Validation** → `app.integrations.spotify.oauth.validate_state()` - CSRF protection for OAuth flow

### Background Tasks

- **Token Refresh Cron** → `app.cron.spotify_refresh.main()` - Proactive token renewal for all users
- **Token Refresh Helper** → `app.integrations.spotify.refresh.SpotifyRefreshHelper.refresh_spotify_token()` - On-demand token refresh
- **Budget Manager** → `app.integrations.spotify.budget.get_spotify_budget_manager()` - Rate limiting and timeout management

### Skills Integration

- **Music Skill** → `app.skills.music_skill.MusicSkill` - Natural language music control via regex patterns
- **Music Orchestrator** → `app.music.orchestrator.MusicOrchestrator` - Provider abstraction for multi-service music control

## Internal Dependencies

### Core Spotify Modules
- **`app.integrations.spotify.client.SpotifyClient`** - Main Web API client with token management and error handling
- **`app.integrations.spotify.oauth.SpotifyOAuth`** - OAuth 2.0 with PKCE implementation
- **`app.integrations.spotify.refresh.SpotifyRefreshHelper`** - Token refresh coordination and error recovery
- **`app.integrations.spotify.budget.SpotifyBudgetManager`** - Rate limiting and timeout management

### Music Control System
- **`app.music.providers.spotify_provider.SpotifyProvider`** - Provider implementation for Spotify playback
- **`app.music.orchestrator.MusicOrchestrator`** - Orchestration layer for music commands
- **`app.music.store`** - Idempotency and state management for music operations

### Token Management
- **`app.auth_store_tokens.TokenDAO`** - SQLite-based token storage and retrieval
- **`app.models.third_party_tokens.ThirdPartyToken`** - Token data model with encryption
- **`app.token_store`** - Redis-based token storage for distributed deployments

### API Layer
- **`app.api.spotify`** - OAuth endpoints and callback handling
- **`app.api.music`** - Music control endpoints with provider abstraction
- **`app.api.spotify_player`** - Legacy Spotify player endpoints
- **`app.api.spotify_sdk`** - SDK-based Spotify integration endpoints

### Skills and Home Assistant
- **`app.skills.music_skill.MusicSkill`** - Regex-based music command parsing
- **`app.home_assistant`** - HA integration for device control fallback
- **`app.skills.parsers.resolve_entity`** - Entity resolution for music commands

## External Dependencies

### Spotify APIs
- **Spotify Web API** - RESTful API for music metadata, playback control, and user data
- **Spotify Accounts API** - OAuth 2.0 authorization and token management
- **Spotify Connect** - Device discovery and cross-device playback control

### Storage Systems
- **SQLite** - Local token storage via `auth_store_tokens.db`
- **Redis** - Distributed token storage for production deployments
- **File system** - Configuration files and temporary OAuth state storage

### Third-party Libraries
- **httpx** - Async HTTP client for Spotify API communication
- **cryptography** - PKCE challenge generation and token encryption
- **base64** - URL-safe encoding for OAuth parameters
- **hashlib** - SHA256 hashing for PKCE and token integrity

### Environment Configuration
- **SPOTIFY_CLIENT_ID** - Spotify application client identifier
- **SPOTIFY_CLIENT_SECRET** - Spotify application client secret
- **SPOTIFY_REDIRECT_URI** - OAuth callback URL for token exchange
- **SPOTIFY_SCOPES** - Requested OAuth scopes (user-read-playback-state, etc.)
- **SPOTIFY_REFRESH_AHEAD_SECONDS** - Proactive token refresh threshold

## Invariants / Assumptions

- **PKCE Security**: OAuth flow always uses PKCE with cryptographically secure verifier generation
- **Token Storage Priority**: Access tokens stored in `auth_store_tokens` table with user_id/provider indexing
- **Refresh Token Security**: Refresh tokens encrypted at rest and only used for token renewal
- **Rate Limit Awareness**: All API calls respect Spotify's rate limits with exponential backoff
- **Scope Validation**: Token scopes validated before API calls requiring specific permissions
- **Device Availability**: Playback operations assume at least one active Spotify device
- **Premium Requirements**: Certain features (transfer playback, volume control) require Spotify Premium
- **Token Expiry Handling**: Access tokens refreshed automatically 5 minutes before expiry
- **State Parameter Security**: OAuth state parameter used for CSRF protection in callback
- **Budget Constraints**: API calls respect global budget limits and timeout constraints

## Known Weirdness / Bugs

- **PKCE State Storage**: PKCE challenges stored in memory without persistence across restarts
- **Token Refresh Race**: Concurrent requests may trigger duplicate refresh attempts
- **Device Discovery Latency**: Initial device enumeration may be slow on large device lists
- **Playback Transfer Reliability**: Device transfer operations may fail silently on network issues
- **Scope Granularity Issues**: Some advanced features may require broader scope permissions
- **Error Response Inconsistency**: Different error formats returned from various API layers
- **Budget Manager Memory**: Per-user budget managers cached indefinitely without cleanup
- **OAuth Callback Validation**: State parameter validation may be bypassed in some edge cases
- **WebSocket Integration Gaps**: WebSocket connections don't properly sync with Spotify state changes
- **Legacy Endpoint Confusion**: Multiple API endpoints for similar functionality with different contracts

## Observed Behavior

### OAuth Flow States

**Authorization Initiation:**
```python
# Generate PKCE challenge-response pair
verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=')

# Create authorization URL
url = f"https://accounts.spotify.com/authorize?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&scope={scopes}&state={state}&code_challenge={challenge}&code_challenge_method=S256"
```

**Token Exchange:**
```python
# Exchange authorization code for tokens
response = await httpx.post("https://accounts.spotify.com/api/token", data={
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": redirect_uri,
    "client_id": client_id,
    "client_secret": client_secret,
    "code_verifier": verifier  # PKCE verification
})
```

**Token Storage:**
```python
# Store tokens in unified token store
token_data = ThirdPartyToken(
    user_id=user_id,
    provider="spotify",
    access_token=access_token,
    refresh_token=refresh_token,
    expires_at=time.time() + expires_in,
    scope=scope
)
await upsert_token(token_data)
```

### Playback Control Flow

**Device Discovery:**
```json
{
  "devices": [
    {
      "id": "device_id_123",
      "is_active": true,
      "name": "Living Room Speaker",
      "type": "Speaker",
      "volume_percent": 75
    }
  ]
}
```

**Playback Commands:**
```json
// Play track
PUT /v1/me/player/play
{
  "uris": ["spotify:track:4iV5W9uYEdYUVa79Axb7Rh"],
  "position_ms": 0
}

// Transfer playback
PUT /v1/me/player
{
  "device_ids": ["device_id_123"],
  "play": true
}
```

**State Retrieval:**
```json
{
  "device": {
    "id": "device_id_123",
    "name": "Living Room Speaker",
    "type": "Speaker",
    "volume_percent": 75
  },
  "shuffle_state": false,
  "repeat_state": "off",
  "timestamp": 1640995200000,
  "context": {
    "type": "playlist",
    "href": "https://api.spotify.com/v1/playlists/playlist_id",
    "uri": "spotify:playlist:playlist_id"
  },
  "progress_ms": 25000,
  "item": {
    "name": "Song Title",
    "artists": [{"name": "Artist Name"}],
    "album": {"name": "Album Name"},
    "duration_ms": 180000,
    "uri": "spotify:track:track_id"
  },
  "currently_playing_type": "track",
  "is_playing": true
}
```

### Error Handling Patterns

**Authentication Errors:**
- **401 Unauthorized**: Token expired or invalid → automatic refresh attempt
- **403 Forbidden**: Insufficient scope → scope validation failure
- **429 Too Many Requests**: Rate limited → exponential backoff with Retry-After header

**Playback Errors:**
- **404 Not Found**: Track/album/playlist not found → entity resolution failure
- **403 Premium Required**: Premium feature attempted on free account → feature gating
- **502 Bad Gateway**: Spotify API temporarily unavailable → circuit breaker activation

**OAuth Errors:**
- **invalid_grant**: Authorization code expired or used → OAuth flow restart required
- **invalid_client**: Client credentials invalid → configuration error
- **access_denied**: User denied authorization → graceful failure handling

### Response Status Codes

- **200 OK**: Successful operation (playback control, state retrieval)
- **201 Created**: New playlist or resource created
- **202 Accepted**: Asynchronous operation accepted (some playback commands)
- **204 No Content**: Successful operation with no response body (pause, skip)
- **400 Bad Request**: Invalid request parameters or malformed data
- **401 Unauthorized**: Authentication required or token invalid
- **403 Forbidden**: Insufficient permissions or scope
- **404 Not Found**: Resource not found (track, album, device)
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Spotify API or internal server error
- **502 Bad Gateway**: Spotify API temporarily unavailable
- **503 Service Unavailable**: Service maintenance or overload

### Circuit Breaker Behavior

- **Failure Threshold**: 3 consecutive failures trigger circuit breaker
- **Cooldown Period**: 60 seconds before attempting recovery
- **Health Check**: Automatic health probes during open circuit state
- **Fallback Strategy**: Graceful degradation with error responses
- **Recovery Logic**: Single success resets failure counter

### Budget Management

**Timeout Scaling:**
```python
# Under budget pressure, reduce timeouts
if budget_state.get("reply_len_target") == "short":
    timeout = min(30.0, 10.0)  # Reduce from 30s to 10s

# Normal budget state
else:
    timeout = 30.0  # Standard 30s timeout
```

**Rate Limit Backoff:**
```python
# Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 60s
delay = min(1.0 * (2 ** attempt), 60.0)
await asyncio.sleep(delay)
```

## TODOs / Redesign Ideas

### Immediate Issues
- **PKCE Persistence**: Store PKCE challenges in Redis to survive application restarts
- **Concurrent Refresh Prevention**: Implement distributed locks to prevent duplicate refresh attempts
- **WebSocket State Sync**: Ensure WebSocket connections receive real-time Spotify state updates
- **Error Response Standardization**: Unify error response formats across all API layers
- **Budget Manager Cleanup**: Implement TTL-based cleanup for cached budget managers

### Architecture Improvements
- **Unified Music API**: Consolidate multiple music endpoints into single consistent API
- **Provider Abstraction**: Strengthen provider interface for easier multi-service support
- **Token Encryption**: Implement proper encryption for stored refresh tokens
- **OAuth State Storage**: Move OAuth state from cookies to server-side storage
- **Device Caching**: Implement intelligent device list caching with invalidation

### Security Enhancements
- **Scope Minimization**: Implement just-in-time scope requests based on operation
- **Token Rotation**: Add automatic token rotation for enhanced security
- **Device Authorization**: Require explicit device authorization for new devices
- **Audit Logging**: Add comprehensive audit logging for all Spotify operations
- **CSRF Protection**: Strengthen CSRF protection for OAuth callback endpoints

### Observability Improvements
- **Playback Metrics**: Add detailed metrics for playback success/failure rates
- **OAuth Flow Monitoring**: Track OAuth flow completion rates and failure points
- **Device Health Monitoring**: Monitor device connectivity and availability
- **Token Health Dashboard**: Create dashboard for token expiry and refresh status
- **Rate Limit Visibility**: Expose rate limiting status and backoff state

### Future Capabilities
- **Multi-Device Playback**: Support synchronized playback across multiple devices
- **Playlist Management**: Full playlist creation, modification, and sharing features
- **Social Features**: Integration with Spotify social features (following, sharing)
- **Audio Analysis**: Leverage Spotify's audio analysis API for enhanced features
- **Queue Management**: Advanced queue manipulation and playlist queueing
- **Context Awareness**: Smart playback based on user context and preferences
- **Cross-Platform Sync**: Synchronize playback state across multiple platforms
- **Advanced Search**: Enhanced search with natural language processing
- **Recommendation Engine**: Integration with Spotify's recommendation algorithms
