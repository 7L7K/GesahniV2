"""
WebSocket Timeout Middleware for consistent timeout handling.

This middleware provides centralized timeout configuration for WebSocket connections:
- Configurable heartbeat intervals
- Connection idle timeouts
- Message send timeouts
- Graceful connection cleanup
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class WebSocketTimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to configure WebSocket timeouts and connection management.
    
    This middleware doesn't intercept WebSocket connections directly (since they're
    handled by FastAPI's WebSocket routing), but provides configuration utilities
    and timeout constants for WebSocket endpoints.
    """

    def __init__(self, app: Any):
        super().__init__(app)
        
        # WebSocket timeout configuration
        self.heartbeat_interval = float(
            os.getenv("WS_HEARTBEAT_INTERVAL", "30.0")
        )  # seconds
        self.connection_timeout = float(
            os.getenv("WS_CONNECTION_TIMEOUT", "300.0")
        )  # 5 minutes
        self.message_timeout = float(
            os.getenv("WS_MESSAGE_TIMEOUT", "1.0")
        )  # seconds
        self.idle_timeout = float(
            os.getenv("WS_IDLE_TIMEOUT", "60.0")
        )  # seconds
        
        # Ping/pong configuration
        self.ping_interval = float(
            os.getenv("WS_PING_INTERVAL", "25.0")
        )  # seconds
        self.pong_timeout = float(
            os.getenv("WS_PONG_TIMEOUT", "60.0")
        )  # seconds
        
        logger.info(
            "WebSocket timeout middleware configured",
            extra={
                "meta": {
                    "heartbeat_interval": self.heartbeat_interval,
                    "connection_timeout": self.connection_timeout,
                    "message_timeout": self.message_timeout,
                    "idle_timeout": self.idle_timeout,
                    "ping_interval": self.ping_interval,
                    "pong_timeout": self.pong_timeout,
                }
            }
        )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Process request - this middleware mainly provides configuration."""
        # For HTTP requests, just pass through
        if request.url.path.startswith("/ws/"):
            # Store timeout config in request state for WebSocket handlers to use
            request.state.ws_timeouts = {
                "heartbeat_interval": self.heartbeat_interval,
                "connection_timeout": self.connection_timeout,
                "message_timeout": self.message_timeout,
                "idle_timeout": self.idle_timeout,
                "ping_interval": self.ping_interval,
                "pong_timeout": self.pong_timeout,
            }
        
        return await call_next(request)


# WebSocket timeout utilities for use in WebSocket endpoints
class WebSocketTimeoutManager:
    """Utility class for managing WebSocket timeouts in endpoints."""
    
    def __init__(self, ws: WebSocket, user_id: str):
        self.ws = ws
        self.user_id = user_id
        self.connected_at = time.monotonic()
        self.last_activity = time.monotonic()
        self.last_pong = time.monotonic()
        
        # Get timeout configuration from environment or defaults
        self.heartbeat_interval = float(os.getenv("WS_HEARTBEAT_INTERVAL", "30.0"))
        self.connection_timeout = float(os.getenv("WS_CONNECTION_TIMEOUT", "300.0"))
        self.message_timeout = float(os.getenv("WS_MESSAGE_TIMEOUT", "1.0"))
        self.idle_timeout = float(os.getenv("WS_IDLE_TIMEOUT", "60.0"))
        self.ping_interval = float(os.getenv("WS_PING_INTERVAL", "25.0"))
        self.pong_timeout = float(os.getenv("WS_PONG_TIMEOUT", "60.0"))

    async def send_json_with_timeout(self, data: dict, timeout: float | None = None) -> bool:
        """Send JSON data with timeout protection."""
        if timeout is None:
            timeout = self.message_timeout
        
        try:
            await asyncio.wait_for(
                self.ws.send_json(data), 
                timeout=timeout
            )
            self.update_activity()
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket send timeout",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "timeout": timeout,
                        "data_type": type(data).__name__,
                    }
                }
            )
            return False
        except Exception as e:
            logger.error(
                "WebSocket send error",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                }
            )
            return False

    async def send_text_with_timeout(self, text: str, timeout: float | None = None) -> bool:
        """Send text data with timeout protection."""
        if timeout is None:
            timeout = self.message_timeout
        
        try:
            await asyncio.wait_for(
                self.ws.send_text(text), 
                timeout=timeout
            )
            self.update_activity()
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket send text timeout",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "timeout": timeout,
                        "text_length": len(text),
                    }
                }
            )
            return False
        except Exception as e:
            logger.error(
                "WebSocket send text error",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                }
            )
            return False

    async def receive_with_timeout(self, timeout: float | None = None) -> str | None:
        """Receive data with timeout protection."""
        if timeout is None:
            timeout = self.ping_interval
        
        try:
            # Wait for either text data or timeout
            done, pending = await asyncio.wait(
                {asyncio.create_task(self.ws.receive_text())},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            if done:
                result = await next(iter(done))
                self.update_activity()
                return result
            else:
                # Timeout occurred
                for task in pending:
                    task.cancel()
                return None
                
        except Exception as e:
            logger.error(
                "WebSocket receive error",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                }
            )
            return None

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.monotonic()
        self.last_pong = time.monotonic()

    def is_idle(self) -> bool:
        """Check if connection has been idle too long."""
        return (time.monotonic() - self.last_activity) > self.idle_timeout

    def is_pong_timeout(self) -> bool:
        """Check if pong response is overdue."""
        return (time.monotonic() - self.last_pong) > self.pong_timeout

    def should_ping(self) -> bool:
        """Check if it's time to send a ping."""
        return (time.monotonic() - self.last_pong) > self.ping_interval

    def connection_age(self) -> float:
        """Get connection age in seconds."""
        return time.monotonic() - self.connected_at

    def is_connection_timeout(self) -> bool:
        """Check if connection has exceeded maximum lifetime."""
        return self.connection_age() > self.connection_timeout

    async def handle_heartbeat(self) -> bool:
        """Handle heartbeat ping/pong cycle."""
        if not self.should_ping():
            return True
        
        try:
            # Send ping
            await self.send_text_with_timeout("ping", timeout=0.5)
            
            # Wait for pong with timeout
            response = await self.receive_with_timeout(timeout=5.0)
            
            if response == "pong":
                self.update_activity()
                return True
            else:
                logger.warning(
                    "WebSocket heartbeat failed - no pong response",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "response": response,
                        }
                    }
                )
                return False
                
        except Exception as e:
            logger.error(
                "WebSocket heartbeat error",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                }
            )
            return False

    async def graceful_close(self, code: int = 1000, reason: str = "normal_closure"):
        """Gracefully close WebSocket connection."""
        try:
            await self.ws.close(code=code, reason=reason)
            logger.info(
                "WebSocket connection closed gracefully",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "code": code,
                        "reason": reason,
                        "connection_age": self.connection_age(),
                    }
                }
            )
        except Exception as e:
            logger.error(
                "Error closing WebSocket connection",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                }
            )


# Import os at module level
import os
