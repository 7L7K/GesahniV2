"""
WebSocket Connection Manager

Centralized WebSocket connection state management with:
- Connection lifecycle tracking
- Heartbeat monitoring
- Graceful cleanup
- Connection health checks
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .ws_metrics import (
    record_ws_broadcast,
    record_ws_broadcast_failed,
    record_ws_connection,
    record_ws_disconnection,
    record_ws_error,
    record_ws_heartbeat_failed,
    record_ws_heartbeat_sent,
    record_ws_message_failed,
    record_ws_message_sent,
)

logger = logging.getLogger(__name__)


@dataclass
class WSConnectionState:
    """Tracks the state of a WebSocket connection."""

    websocket: WebSocket
    user_id: str
    connected_at: float
    last_activity: float
    heartbeat_interval: float = 30.0
    max_idle_time: float = 300.0  # 5 minutes
    is_alive: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.websocket_ref = weakref.ref(self.websocket)
        self.last_heartbeat = time.monotonic()

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.monotonic()
        self.last_heartbeat = time.monotonic()

    def is_idle(self) -> bool:
        """Check if connection has been idle too long."""
        return (time.monotonic() - self.last_activity) > self.max_idle_time

    def should_ping(self) -> bool:
        """Check if it's time to send a ping."""
        return (time.monotonic() - self.last_heartbeat) > self.heartbeat_interval

    async def ping(self) -> bool:
        """Send a ping and return True if successful."""
        try:
            await self.websocket.send_text("ping")
            self.last_heartbeat = time.monotonic()
            record_ws_heartbeat_sent()
            return True
        except Exception as e:
            logger.debug("ws.ping.failed: user_id=%s error=%s", self.user_id, str(e))
            self.is_alive = False
            record_ws_heartbeat_failed()
            record_ws_error(
                "heartbeat_failed", self.metadata.get("endpoint", "unknown")
            )
            return False

    async def close(self, code: int = 1000, reason: str = "normal_closure"):
        """Close the WebSocket connection gracefully."""
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception as e:
            logger.debug("ws.close.error: user_id=%s error=%s", self.user_id, str(e))
        finally:
            self.is_alive = False


class WSConnectionManager:
    """Centralized WebSocket connection manager."""

    def __init__(self):
        self._connections: dict[str, WSConnectionState] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self):
        """Start background cleanup and heartbeat tasks."""
        async with self._lock:
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            if self._heartbeat_task is None:
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """Stop background tasks and close all connections."""
        async with self._lock:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Close all connections
            for conn_state in list(self._connections.values()):
                await conn_state.close()

            self._connections.clear()

    async def add_connection(
        self, ws: WebSocket, user_id: str, **metadata
    ) -> WSConnectionState:
        """Add a new WebSocket connection."""
        async with self._lock:
            # Remove any existing connection for this user
            if user_id in self._connections:
                old_conn = self._connections[user_id]
                await old_conn.close(code=1000, reason="replaced_by_new_connection")

            conn_state = WSConnectionState(
                websocket=ws,
                user_id=user_id,
                connected_at=time.monotonic(),
                last_activity=time.monotonic(),
                metadata=metadata,
            )

            self._connections[user_id] = conn_state

            # Record metrics
            endpoint = metadata.get("endpoint", "unknown")
            record_ws_connection(endpoint, user_id)

            logger.info(
                "ws.manager.add: user_id=%s endpoint=%s connections=%d",
                user_id,
                endpoint,
                len(self._connections),
            )
            return conn_state

    async def remove_connection(self, user_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if user_id in self._connections:
                conn_state = self._connections[user_id]
                duration = time.monotonic() - conn_state.connected_at
                endpoint = conn_state.metadata.get("endpoint", "unknown")

                await conn_state.close()
                del self._connections[user_id]

                # Record metrics
                record_ws_disconnection(endpoint, user_id, duration)

                logger.info(
                    "ws.manager.remove: user_id=%s endpoint=%s duration=%.2f connections=%d",
                    user_id,
                    endpoint,
                    duration,
                    len(self._connections),
                )

    def get_connection(self, user_id: str) -> WSConnectionState | None:
        """Get connection state for a user."""
        return self._connections.get(user_id)

    def get_all_connections(self) -> list[WSConnectionState]:
        """Get all active connections."""
        return list(self._connections.values())

    def get_connections_by_metadata(
        self, key: str, value: Any
    ) -> list[WSConnectionState]:
        """Get connections filtered by metadata."""
        return [
            conn
            for conn in self._connections.values()
            if conn.metadata.get(key) == value
        ]

    async def broadcast_to_all(
        self, message: dict, exclude_user_ids: set[str] | None = None
    ):
        """Broadcast message to all connections."""
        exclude = exclude_user_ids or set()
        connections = [
            conn
            for uid, conn in self._connections.items()
            if uid not in exclude and conn.is_alive
        ]

        if not connections:
            return

        # Record broadcast attempt
        record_ws_broadcast()

        failed_count = 0

        async def send_to_connection(conn: WSConnectionState):
            nonlocal failed_count
            try:
                await conn.websocket.send_json(message)
                conn.update_activity()
                record_ws_message_sent()
            except Exception as e:
                logger.debug(
                    "ws.broadcast.failed: user_id=%s error=%s", conn.user_id, str(e)
                )
                conn.is_alive = False
                failed_count += 1
                record_ws_message_failed()
                record_ws_error(
                    "broadcast_send_failed", conn.metadata.get("endpoint", "unknown")
                )

        await asyncio.gather(
            *[send_to_connection(conn) for conn in connections], return_exceptions=True
        )

        if failed_count > 0:
            record_ws_broadcast_failed()

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send message to specific user."""
        conn = self._connections.get(user_id)
        if not conn or not conn.is_alive:
            record_ws_message_failed()
            return False

        try:
            await conn.websocket.send_json(message)
            conn.update_activity()
            record_ws_message_sent()
            return True
        except Exception as e:
            logger.debug("ws.send.failed: user_id=%s error=%s", user_id, str(e))
            conn.is_alive = False
            record_ws_message_failed()
            record_ws_error(
                "send_to_user_failed", conn.metadata.get("endpoint", "unknown")
            )
            return False

    async def _cleanup_loop(self):
        """Background task to clean up idle and dead connections."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ws.cleanup.error: %s", str(e))

    async def _heartbeat_loop(self):
        """Background task to send heartbeats and check connection health."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._send_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ws.heartbeat.error: %s", str(e))

    async def _cleanup_idle_connections(self):
        """Remove idle connections."""
        async with self._lock:
            idle_connections = []
            for user_id, conn in list(self._connections.items()):
                if conn.is_idle():
                    idle_connections.append((user_id, conn))

            for user_id, conn in idle_connections:
                logger.info(
                    "ws.cleanup.idle: user_id=%s idle_time=%.1fs",
                    user_id,
                    time.monotonic() - conn.last_activity,
                )
                await conn.close(code=1000, reason="idle_timeout")
                del self._connections[user_id]

    async def _send_heartbeats(self):
        """Send heartbeats to connections that need them."""
        connections_to_ping = []
        async with self._lock:
            for conn in list(self._connections.values()):
                if conn.should_ping():
                    connections_to_ping.append(conn)

        for conn in connections_to_ping:
            success = await conn.ping()
            if not success:
                # Connection failed ping, will be cleaned up in next cleanup cycle
                logger.debug("ws.heartbeat.failed: user_id=%s", conn.user_id)


# Global connection manager instance
ws_manager = WSConnectionManager()


async def get_ws_manager() -> WSConnectionManager:
    """Dependency injection for WebSocket manager."""
    return ws_manager
