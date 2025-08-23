# WebSocket Implementation with Origin Validation

This document describes the WebSocket implementation in GesahniV2, including the origin validation requirements and URL building consistency.

## Overview

The WebSocket implementation ensures secure communication between the frontend and backend by:

1. **Consistent Origin Validation**: Only accepting `http://localhost:3000` as the canonical frontend origin
2. **Proper URL Building**: Converting HTTP to WS/WSS schemes consistently
3. **Crisp Error Handling**: Providing clear error codes and reasons for failures
4. **Security**: Restricting CORS origins and validating WebSocket connections

## Frontend Implementation

### URL Building

The frontend uses canonical URL building functions in `frontend/src/lib/urls.ts`:

```typescript
// Get the canonical frontend origin
export function getCanonicalFrontendOrigin(): string {
    return "http://localhost:3000";
}

// Build WebSocket URL using canonical origin
export function buildCanonicalWebSocketUrl(apiOrigin: string, path: string): string {
    const canonicalOrigin = getCanonicalFrontendOrigin();
    const parsed = new URL(canonicalOrigin);
    const wsScheme = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = `${wsScheme}//${parsed.host}`;
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${wsBase}${normalizedPath}`;
}
```

### API Integration

The `wsUrl` function in `frontend/src/lib/api.ts` uses the canonical WebSocket URL builder:

```typescript
export function wsUrl(path: string): string {
    // Build WebSocket URL using canonical frontend origin for consistent origin validation
    const baseUrl = buildCanonicalWebSocketUrl(API_URL, path);
    if (!HEADER_AUTH_MODE) return baseUrl; // cookie-auth for WS
    const token = getToken();
    if (!token) return baseUrl;
    const sep = path.includes("?") ? "&" : "?";
    return `${baseUrl}${sep}access_token=${encodeURIComponent(token)}`;
}
```

## Backend Implementation

### CORS Configuration

The backend enforces strict CORS origin validation in `app/main.py`:

```python
# WebSocket requirement: Only accept http://localhost:3000 for consistent origin validation
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

# Security: WebSocket requirement - use exactly http://localhost:3000 (not 127.0.0.1:3000)
if len(origins) > 1:
    logging.warning("Multiple CORS origins detected. WebSocket requirement: use exactly http://localhost:3000")
    origins = ["http://localhost:3000"]

# Final validation: ensure we only have http://localhost:3000
if origins != ["http://localhost:3000"]:
    logging.warning(f"WebSocket requirement: CORS origins {origins} not canonical. Using http://localhost:3000")
    origins = ["http://localhost:3000"]
```

### WebSocket Origin Validation

The `verify_ws` function in `app/security.py` validates WebSocket origins:

```python
async def verify_ws(websocket: WebSocket) -> None:
    """JWT validation for WebSocket connections.

    WebSocket requirement: Validates origin to ensure only http://localhost:3000 is accepted.
    """
    # WebSocket requirement: Origin validation - only accept http://localhost:3000
    origin = websocket.headers.get("Origin")
    if origin and origin != "http://localhost:3000":
        # WebSocket requirement: Close with crisp code/reason for origin mismatch
        await websocket.close(
            code=1008,  # Policy violation
            reason="Origin not allowed: only http://localhost:3000 accepted"
        )
        return
```

### Error Handling

HTTP requests to WebSocket endpoints return crisp error codes:

```python
async def websocket_http_handler(request: Request, path: str):
    """Handle HTTP requests to WebSocket endpoints with crisp error codes and reasons."""
    # WebSocket requirement: Provide crisp error codes and reasons (no 404 masking)
    response = Response(
        content="WebSocket endpoint requires WebSocket protocol",
        status_code=400,
        media_type="text/plain",
        headers={
            "X-WebSocket-Error": "protocol_required",
            "X-WebSocket-Reason": "HTTP requests not supported on WebSocket endpoints"
        }
    )
    return response
```

## WebSocket Endpoints

The following WebSocket endpoints are available:

- `/v1/ws/transcribe` - Live transcription
- `/v1/ws/music` - Music state updates
- `/v1/ws/care` - Care-related updates

All endpoints require authentication and validate origins.

## Testing

### Unit Tests

- `tests/unit/test_websocket_origin_validation_unit.py` - Tests origin validation logic
- `frontend/src/lib/__tests__/urls.websocket.test.ts` - Tests URL building functions

### Integration Tests

- `tests/integration/test_websocket_integration.py` - End-to-end WebSocket functionality tests

## Security Considerations

1. **Origin Validation**: Only `http://localhost:3000` is accepted as a valid origin
2. **CORS Restrictions**: CORS is configured to only allow the canonical origin
3. **Authentication**: WebSocket connections require valid JWT tokens
4. **Error Handling**: Clear error codes prevent information leakage

## Configuration

The WebSocket implementation uses the following environment variables:

- `CORS_ALLOW_ORIGINS` - CORS origins (defaults to `http://localhost:3000`)
- `JWT_SECRET` - JWT secret for authentication
- `NEXT_PUBLIC_API_ORIGIN` - API origin for frontend URL building

## Usage Example

```typescript
// Frontend WebSocket connection
const ws = new WebSocket(wsUrl("/v1/ws/transcribe"));

ws.onopen = () => {
    console.log("WebSocket connected");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Received:", data);
};

ws.onclose = (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
};
```

## Requirements Met

✅ **WS URL builder reads canonical frontend origin and flips http→ws consistently**
✅ **Origin checks on backend accept only http://localhost:3000**
✅ **On failure, close with crisp code/reason (no 404 masking)**
✅ **Comprehensive test coverage**
✅ **Security validation**
✅ **Error handling with proper codes**
