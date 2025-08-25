# Spotify Integration

This module provides a complete Spotify integration for GesahniV2 with OAuth 2.0, PKCE, unified token storage, and Web API client functionality.

## Features

- **PKCE OAuth Flow**: Server-assisted PKCE with secure challenge generation
- **Unified Token Storage**: All tokens stored in SQLite database with encryption
- **Automatic Token Refresh**: Handles token expiration and refresh automatically
- **Budget & Timeout Support**: Respects router budget and implements Retry-After backoff
- **Circuit Breaker**: Protects against cascading failures
- **Web Playback SDK Support**: Backend proxy for Web Playback SDK (behind feature flag)

## Setup

### Environment Variables

```bash
# Required
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/api/spotify/callback

# Optional
SPOTIFY_SCOPES=user-read-playback-state user-modify-playback-state streaming playlist-read-private playlist-modify-private
ENABLE_SPOTIFY_WEB_SDK=0
THIRD_PARTY_TOKENS_DB=third_party_tokens.db
ROUTER_BUDGET_MS=30000
```

### Database Migration

Run the migration script to move from JSON files to the unified database:

```bash
# Preview migration
python scripts/migrate_spotify_tokens.py --dry-run

# Perform migration
python scripts/migrate_spotify_tokens.py --migrate

# Rollback if needed
python scripts/migrate_spotify_tokens.py --rollback
```

## API Endpoints

### OAuth Flow
- `GET /api/spotify/connect` - Initiate OAuth flow
- `GET /api/spotify/callback` - Handle OAuth callback
- `DELETE /api/spotify/disconnect` - Disconnect Spotify
- `GET /api/spotify/status` - Get connection status

### Web API Client Methods

```python
from app.integrations.spotify.client import SpotifyClient

client = SpotifyClient(user_id)

# Playback control
await client.play(uris=["spotify:track:4uLU6hMCjMI75M1A2tKUQC"])
await client.pause()
await client.next_track()
await client.previous_track()
await client.set_volume(50)

# Device management
devices = await client.get_devices()
await client.transfer_playback(device_id)

# Current state
state = await client.get_currently_playing()
queue = await client.get_queue()

# Recommendations
tracks = await client.get_recommendations(
    seed_tracks=["spotify:track:4uLU6hMCjMI75M1A2tKUQC"],
    target_energy=0.8,
    target_tempo=120
)
```

## Architecture

### Provider Pattern
```
app/integrations/spotify/
├── __init__.py          # Module exports
├── oauth.py             # PKCE OAuth implementation
├── client.py            # Web API client with token management
├── refresh.py           # Generic refresh helpers
└── README.md           # This file
```

### Token Storage
- All tokens stored in `third_party_tokens` table
- Automatic encryption using `MUSIC_MASTER_KEY`
- Soft delete with `is_valid` flag
- Indexed for efficient lookups

### Error Handling
- `SpotifyAuthError`: Authentication failures
- `SpotifyOAuthError`: OAuth flow errors
- Automatic retry with exponential backoff
- Circuit breaker for cascading failure protection

## Scopes

### Minimal Scopes (Recommended)
- `user-read-playback-state`: Read playback state
- `user-modify-playback-state`: Control playback
- `streaming`: Web Playback SDK
- `playlist-read-private`: Read private playlists
- `playlist-modify-private`: Modify private playlists

### Non-Premium UX
- Read-only fallback for non-premium users
- Search and browse functionality remains available
- Playback controls show premium banner
- Graceful degradation for unsupported features

## Web Playback SDK Integration

When `ENABLE_SPOTIFY_WEB_SDK=1`:

1. Backend proxies all Web API calls
2. Web Playback SDK loads in TV view
3. All authentication handled server-side
4. Seamless integration with existing UI

## Development

### Testing
```bash
# Test OAuth flow
pytest tests/test_spotify_oauth.py

# Test client functionality
pytest tests/test_spotify_client.py

# Test token storage
pytest tests/test_token_storage.py
```

### Local Development
1. Set up Spotify app at https://developer.spotify.com
2. Configure redirect URI: `http://localhost:8000/api/spotify/callback`
3. Set environment variables
4. Run migration script
5. Test OAuth flow: `GET /api/spotify/connect`

## Security Considerations

- PKCE prevents authorization code interception
- All tokens encrypted in database
- Automatic token expiration handling
- CSRF protection with state parameter
- Rate limiting and budget enforcement
- Circuit breaker prevents abuse

## Migration from Legacy Implementation

The legacy JSON-based token storage has been replaced with a unified database approach:

1. **Before**: Tokens in `data/spotify_tokens/{user_id}.json`
2. **After**: Tokens in `third_party_tokens` table
3. **Migration**: Run `scripts/migrate_spotify_tokens.py`

Benefits:
- Centralized token management
- Better security with encryption
- Scalable for multiple providers
- Atomic operations with transactions
- Efficient indexing and querying
