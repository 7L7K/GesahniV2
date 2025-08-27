#!/usr/bin/env python3
"""
Spotify Integration Debugger

This module provides comprehensive debugging, logging, and health check
capabilities for the Spotify integration without cluttering the main code
with debug statements.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set up structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)

@dataclass
class SpotifyDebugEvent:
    """Structured debug event for Spotify operations."""
    timestamp: float = field(default_factory=time.time)
    operation: str = ""
    user_id: str = ""
    status: str = ""
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "user_id": self.user_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata
        }

class SpotifyDebugger:
    """Centralized debugger for Spotify integration."""

    def __init__(self):
        self.logger = logging.getLogger("spotify.debugger")
        self.events: List[SpotifyDebugEvent] = []
        self._health_checks = {}
        self._active_operations = {}

    def log_event(self, event: SpotifyDebugEvent):
        """Log a structured debug event."""
        self.events.append(event)
        self.logger.info(f"SPOTIFY_EVENT: {event.operation} | {event.status} | {event.user_id}")

        if event.error:
            self.logger.error(f"SPOTIFY_ERROR: {event.operation} | {event.error}")

    @asynccontextmanager
    async def track_operation(self, operation: str, user_id: str = "unknown"):
        """Context manager to track operation timing and errors."""
        start_time = time.time()
        operation_id = f"{operation}_{user_id}_{int(start_time * 1000)}"
        self._active_operations[operation_id] = start_time

        try:
            yield operation_id
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            event = SpotifyDebugEvent(
                operation=operation,
                user_id=user_id,
                status="error",
                duration_ms=duration,
                error=str(e)
            )
            self.log_event(event)
            raise
        else:
            duration = (time.time() - start_time) * 1000
            event = SpotifyDebugEvent(
                operation=operation,
                user_id=user_id,
                status="success",
                duration_ms=duration
            )
            self.log_event(event)
        finally:
            self._active_operations.pop(operation_id, None)

    def register_health_check(self, name: str, check_func):
        """Register a health check function."""
        self._health_checks[name] = check_func

    async def run_health_checks(self) -> Dict[str, Any]:
        """Run all registered health checks."""
        results = {}
        for name, check_func in self._health_checks.items():
            try:
                result = await check_func()
                results[name] = {"status": "healthy", "result": result}
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}

        return results

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent debug events."""
        return [event.to_dict() for event in self.events[-limit:]]

    def get_operation_stats(self) -> Dict[str, Any]:
        """Get statistics about operations."""
        stats = {}
        for event in self.events:
            op = event.operation
            if op not in stats:
                stats[op] = {"count": 0, "success": 0, "error": 0, "avg_duration": 0}

            stats[op]["count"] += 1
            if event.status == "success":
                stats[op]["success"] += 1
            elif event.status == "error":
                stats[op]["error"] += 1

            if event.duration_ms:
                # Simple moving average
                current_avg = stats[op]["avg_duration"]
                count = stats[op]["count"]
                stats[op]["avg_duration"] = (current_avg * (count - 1) + event.duration_ms) / count

        return stats

# Global debugger instance
spotify_debugger = SpotifyDebugger()

# Health check functions
async def check_spotify_credentials():
    """Check if Spotify credentials are configured."""
    import os
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("Spotify credentials not configured")

    return {"client_id_length": len(client_id), "client_secret_length": len(client_secret)}

async def check_spotify_routes():
    """Check if Spotify routes are accessible."""
    import os
    os.environ['TEST_MODE'] = '1'
    os.environ['JWT_OPTIONAL_IN_TESTS'] = '1'

    try:
        from app.main import app
        client = TestClient(app)

        endpoints = [
            "/v1/spotify/status",
            "/v1/spotify/devices",
            "/v1/spotify/token-for-sdk"
        ]

        results = {}
        for endpoint in endpoints:
            try:
                response = client.get(endpoint)
                results[endpoint] = {"status_code": response.status_code}
            except Exception as e:
                results[endpoint] = {"error": str(e)}

        return results
    except Exception as e:
        raise ValueError(f"Could not create test app: {e}")

async def check_spotify_imports():
    """Check if Spotify modules can be imported."""
    modules = [
        "app.api.spotify",
        "app.api.spotify_player",
        "app.api.spotify_sdk",
        "app.integrations.spotify.client",
        "app.integrations.spotify.oauth"
    ]

    results = {}
    for module in modules:
        try:
            exec(f"import {module}")
            results[module] = "ok"
        except Exception as e:
            results[module] = f"error: {e}"

    return results

# Register health checks
spotify_debugger.register_health_check("credentials", check_spotify_credentials)
spotify_debugger.register_health_check("routes", check_spotify_routes)
spotify_debugger.register_health_check("imports", check_spotify_imports)

# Utility functions for main Spotify modules
def debug_log_spotify_request(operation: str, user_id: str = "unknown", **metadata):
    """Helper function to log Spotify requests with structured data."""
    event = SpotifyDebugEvent(
        operation=operation,
        user_id=user_id,
        status="request",
        metadata=metadata
    )
    spotify_debugger.log_event(event)

def debug_log_spotify_response(operation: str, user_id: str = "unknown", status: str = "success", error: str = None, **metadata):
    """Helper function to log Spotify responses."""
    event = SpotifyDebugEvent(
        operation=operation,
        user_id=user_id,
        status=status,
        error=error,
        metadata=metadata
    )
    spotify_debugger.log_event(event)

@asynccontextmanager
async def debug_track_spotify_operation(operation: str, user_id: str = "unknown"):
    """Context manager for tracking Spotify operations."""
    async with spotify_debugger.track_operation(operation, user_id) as op_id:
        yield op_id

# Main debugging interface
async def debug_spotify_integration():
    """Run comprehensive Spotify integration debug."""
    print("🔍 Spotify Integration Debug Report")
    print("=" * 60)

    # Run health checks
    print("\n📊 Health Checks:")
    health_results = await spotify_debugger.run_health_checks()
    for check_name, result in health_results.items():
        status = result["status"]
        icon = "✅" if status == "healthy" else "❌"
        print(f"  {icon} {check_name}: {status}")
        if "error" in result:
            print(f"    Error: {result['error']}")
        elif "result" in result:
            print(f"    Result: {result['result']}")

    # Show recent events
    print("\n📝 Recent Events:")
    recent_events = spotify_debugger.get_recent_events(5)
    if recent_events:
        for event in recent_events:
            status_icon = "✅" if event["status"] == "success" else "❌" if event["status"] == "error" else "🔄"
            duration = f" ({event['duration_ms']:.1f}ms)" if event["duration_ms"] else ""
            print(f"  {status_icon} {event['operation']} | {event['user_id']} | {event['status']}{duration}")
            if event["error"]:
                print(f"    Error: {event['error']}")
    else:
        print("  No events recorded yet")

    # Show operation statistics
    print("\n📈 Operation Statistics:")
    stats = spotify_debugger.get_operation_stats()
    if stats:
        for operation, data in stats.items():
            success_rate = (data["success"] / data["count"]) * 100 if data["count"] > 0 else 0
            print(f"  {operation}: {data['count']} total | {success_rate:.1f}% success | {data['avg_duration']:.1f}ms avg")
    else:
        print("  No operations recorded yet")

    print("\n" + "=" * 60)
    print("Debug report complete.")

def create_debug_routes(app: FastAPI):
    """Add debug routes to FastAPI app."""
    from fastapi import APIRouter

    debug_router = APIRouter(prefix="/debug/spotify", tags=["spotify-debug"])

    @debug_router.get("/health")
    async def get_spotify_health():
        """Get Spotify integration health status."""
        return await spotify_debugger.run_health_checks()

    @debug_router.get("/events")
    async def get_spotify_events(limit: int = 10):
        """Get recent Spotify debug events."""
        return spotify_debugger.get_recent_events(limit)

    @debug_router.get("/stats")
    async def get_spotify_stats():
        """Get Spotify operation statistics."""
        return spotify_debugger.get_operation_stats()

    @debug_router.post("/clear-events")
    async def clear_events():
        """Clear debug events."""
        spotify_debugger.events.clear()
        return {"message": "Events cleared"}

    app.include_router(debug_router)

if __name__ == "__main__":
    # Run debug when script is called directly
    asyncio.run(debug_spotify_integration())

