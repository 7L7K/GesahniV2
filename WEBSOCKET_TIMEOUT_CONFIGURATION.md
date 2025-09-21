# WebSocket Timeout Configuration

This document describes the WebSocket timeout configuration system implemented for consistent timeout handling across all WebSocket endpoints.

## Overview

The WebSocket timeout system provides:
- Configurable heartbeat intervals
- Connection idle timeouts
- Message send timeouts
- Graceful connection cleanup
- Centralized timeout management

## Environment Variables

The following environment variables control WebSocket timeout behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `WS_HEARTBEAT_INTERVAL` | `30.0` | Interval between heartbeat checks (seconds) |
| `WS_CONNECTION_TIMEOUT` | `300.0` | Maximum connection lifetime (seconds) |
| `WS_MESSAGE_TIMEOUT` | `1.0` | Timeout for sending messages (seconds) |
| `WS_IDLE_TIMEOUT` | `60.0` | Timeout for idle connections (seconds) |
| `WS_PING_INTERVAL` | `25.0` | Interval between ping messages (seconds) |
| `WS_PONG_TIMEOUT` | `60.0` | Timeout for pong responses (seconds) |

## Usage in WebSocket Endpoints

### Basic Usage

```python
from app.middleware.websocket_timeout import WebSocketTimeoutManager

@router.websocket("/ws/example")
async def websocket_endpoint(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    await ws.accept()
    
    # Create timeout manager
    timeout_manager = WebSocketTimeoutManager(ws, user_id)
    
    try:
        while True:
            # Receive with timeout
            message = await timeout_manager.receive_with_timeout()
            if message is None:
                # Timeout occurred, send ping
                if not await timeout_manager.handle_heartbeat():
                    break  # Connection lost
                continue
            
            if message == "pong":
                timeout_manager.update_activity()
                continue
            
            # Process message
            response = {"type": "response", "data": "processed"}
            
            # Send with timeout
            if not await timeout_manager.send_json_with_timeout(response):
                break  # Send failed
            
            # Check for connection timeout
            if timeout_manager.is_connection_timeout():
                break
                
    finally:
        await timeout_manager.graceful_close()
```

### Advanced Usage with Custom Timeouts

```python
@router.websocket("/ws/custom")
async def websocket_custom(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    await ws.accept()
    
    timeout_manager = WebSocketTimeoutManager(ws, user_id)
    
    # Custom timeout for this endpoint
    timeout_manager.message_timeout = 5.0  # 5 seconds
    
    try:
        while True:
            # Use custom timeout for receive
            message = await timeout_manager.receive_with_timeout(timeout=10.0)
            
            if message is None:
                # Handle timeout
                continue
            
            # Process message with custom logic
            await process_message(message, timeout_manager)
            
    finally:
        await timeout_manager.graceful_close()
```

## WebSocketTimeoutManager API

### Constructor
```python
WebSocketTimeoutManager(ws: WebSocket, user_id: str)
```

### Methods

#### Message Sending
- `send_json_with_timeout(data: dict, timeout: float | None = None) -> bool`
- `send_text_with_timeout(text: str, timeout: float | None = None) -> bool`

#### Message Receiving
- `receive_with_timeout(timeout: float | None = None) -> str | None`

#### Connection Management
- `update_activity()` - Update last activity timestamp
- `is_idle() -> bool` - Check if connection is idle
- `is_pong_timeout() -> bool` - Check if pong response is overdue
- `should_ping() -> bool` - Check if it's time to send a ping
- `connection_age() -> float` - Get connection age in seconds
- `is_connection_timeout() -> bool` - Check if connection exceeded max lifetime

#### Heartbeat
- `handle_heartbeat() -> bool` - Handle ping/pong cycle

#### Cleanup
- `graceful_close(code: int = 1000, reason: str = "normal_closure")`

## Middleware Integration

The `WebSocketTimeoutMiddleware` is automatically registered in the middleware stack and provides timeout configuration to all requests. The middleware doesn't intercept WebSocket connections directly (since they're handled by FastAPI's routing), but makes timeout configuration available.

## Best Practices

1. **Always use timeout managers** for WebSocket endpoints to ensure consistent behavior
2. **Handle timeouts gracefully** - don't let timeouts crash the connection
3. **Implement proper cleanup** - always call `graceful_close()` in finally blocks
4. **Monitor connection health** - use heartbeat and idle detection
5. **Log timeout events** - the system includes comprehensive logging

## Error Handling

The timeout manager handles various error conditions:
- **Send timeouts** - Returns `False` when sending fails
- **Receive timeouts** - Returns `None` when no data is received
- **Connection timeouts** - Detects when connections exceed maximum lifetime
- **Pong timeouts** - Detects when clients don't respond to pings

## Monitoring and Logging

The system includes comprehensive logging for:
- Connection establishment and cleanup
- Timeout events
- Heartbeat success/failure
- Send/receive errors

Log messages are structured with metadata including user ID, timeout values, and error details.

## Configuration Examples

### Development Environment
```bash
# Shorter timeouts for development
WS_HEARTBEAT_INTERVAL=15.0
WS_CONNECTION_TIMEOUT=120.0
WS_MESSAGE_TIMEOUT=0.5
WS_IDLE_TIMEOUT=30.0
WS_PING_INTERVAL=10.0
WS_PONG_TIMEOUT=30.0
```

### Production Environment
```bash
# Longer timeouts for production stability
WS_HEARTBEAT_INTERVAL=60.0
WS_CONNECTION_TIMEOUT=600.0
WS_MESSAGE_TIMEOUT=2.0
WS_IDLE_TIMEOUT=120.0
WS_PING_INTERVAL=30.0
WS_PONG_TIMEOUT=90.0
```

### High-Latency Environment
```bash
# Extended timeouts for high-latency networks
WS_HEARTBEAT_INTERVAL=120.0
WS_CONNECTION_TIMEOUT=1200.0
WS_MESSAGE_TIMEOUT=5.0
WS_IDLE_TIMEOUT=300.0
WS_PING_INTERVAL=60.0
WS_PONG_TIMEOUT=180.0
```
