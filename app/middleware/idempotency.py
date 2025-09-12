# app/middleware/idempotency.py
import hashlib
import json
import logging
import os
import time
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """Redis-backed store for idempotency keys with TTL."""

    def __init__(self):
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis client if available."""
        try:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                from redis import Redis
                self._redis_client = Redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self._redis_client.ping()
                logger.info("Idempotency store using Redis backend")
            else:
                logger.info("Idempotency store using in-memory backend (no REDIS_URL)")
        except Exception as e:
            logger.warning(f"Redis unavailable for idempotency store, using in-memory: {e}")
            self._redis_client = None

        # In-memory fallback
        self._memory_store: dict[str, Any] = {}

    def _get_key(self, idempotency_key: str, method: str, path: str) -> str:
        """Generate Redis key for idempotency entry."""
        # Create a stable key based on the idempotency key and request details
        raw = f"idempotency:{idempotency_key}:{method}:{path}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def store_response(self, idempotency_key: str, method: str, path: str,
                      status_code: int, content: Any, ttl_seconds: int = 86400) -> None:
        """Store a response for an idempotency key with TTL."""
        cache_key = self._get_key(idempotency_key, method, path)
        data = {
            "status_code": status_code,
            "content": content,
            "timestamp": time.time(),
            "method": method,
            "path": path,
        }

        if self._redis_client:
            try:
                self._redis_client.setex(cache_key, ttl_seconds, json.dumps(data))
            except Exception as e:
                logger.warning(f"Redis error storing idempotency response: {e}")
                # Fall back to memory
                self._memory_store[cache_key] = data
        else:
            # Store in memory
            self._memory_store[cache_key] = data

        logger.debug(f"Stored idempotency response for key {idempotency_key[:8]}...")

    def get_response(self, idempotency_key: str, method: str, path: str) -> dict | None:
        """Retrieve a stored response for an idempotency key."""
        cache_key = self._get_key(idempotency_key, method, path)

        if self._redis_client:
            try:
                data = self._redis_client.get(cache_key)
                if data:
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Corrupt idempotency data for {cache_key}: {e}")
                        # Clean up corrupt data
                        self._redis_client.delete(cache_key)
                        return None
            except Exception as e:
                logger.warning(f"Redis error getting idempotency response: {e}")
                # Fall back to memory
                return self._memory_store.get(cache_key)
        else:
            # Check in-memory store
            return self._memory_store.get(cache_key)

    def cleanup_expired(self):
        """Clean up expired entries from memory store."""
        if not self._redis_client:
            current_time = time.time()
            # Memory store entries don't have TTL, so we don't clean them up automatically
            # They would be cleaned up by Redis TTL when using Redis
            pass


# Global idempotency store instance
_idempotency_store = IdempotencyStore()


def get_idempotency_store() -> IdempotencyStore:
    """Get the global idempotency store instance."""
    return _idempotency_store


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling Idempotency-Key headers on POST/PUT/PATCH/DELETE requests."""

    def __init__(self, app: ASGIApp, ttl_seconds: int = 86400):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
        # Routes that should use idempotency
        self.idempotent_routes = {
            "/v1/ask",  # Main ask endpoint
            "/v1/payments",  # Payment endpoints (if they exist)
            "/v1/payment",  # Alternative payment endpoint
            "/v1/transactions",  # Transaction endpoints
            "/v1/checkout",  # Checkout endpoints
            "/v1/billing",  # Billing endpoints
        }

    def _should_apply_idempotency(self, request: Request) -> bool:
        """Check if idempotency should be applied to this request."""
        # Only apply to POST, PUT, PATCH, DELETE methods
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return False

        # Check if the path matches any of the idempotent routes
        path = request.url.path
        for route in self.idempotent_routes:
            if path.startswith(route):
                return True

        return False

    def _get_idempotency_key(self, request: Request) -> str | None:
        """Extract idempotency key from request headers."""
        return request.headers.get("Idempotency-Key")

    def _create_request_hash(self, request: Request, body: bytes) -> str:
        """Create a hash of the request to detect duplicates."""
        # Hash the method, path, query params, and body
        method = request.method
        path = request.url.path
        query = str(request.url.query)
        body_hash = hashlib.sha256(body).hexdigest()

        combined = f"{method}:{path}:{query}:{body_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()

    async def dispatch(self, request: Request, call_next):
        # Skip if idempotency doesn't apply to this route
        if not self._should_apply_idempotency(request):
            return await call_next(request)

        idempotency_key = self._get_idempotency_key(request)
        if not idempotency_key:
            # No idempotency key provided, proceed normally
            return await call_next(request)

        # Validate idempotency key format (should be UUID-like)
        try:
            # Basic validation - should be at least 8 characters and contain some variety
            if len(idempotency_key) < 8 or len(set(idempotency_key)) < 4:
                logger.warning(f"Invalid idempotency key format: {idempotency_key[:16]}...")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Idempotency-Key format"
                )
        except HTTPException:
            raise
        except Exception:
            logger.warning(f"Invalid idempotency key format: {idempotency_key[:16]}...")
            raise HTTPException(
                status_code=400,
                detail="Invalid Idempotency-Key format"
            )

        # Read the request body for hashing
        body = await request.body()

        # Check if we have a stored response for this idempotency key
        store = get_idempotency_store()
        stored_response = store.get_response(idempotency_key, request.method, request.url.path)

        if stored_response:
            # Create a hash of the current request
            current_request_hash = self._create_request_hash(request, body)

            # If the stored response exists, check if it's for the same request
            stored_hash = stored_response.get("request_hash")
            if stored_hash and stored_hash != current_request_hash:
                # Different request with same idempotency key - conflict
                logger.warning(f"Idempotency key reuse with different request: {idempotency_key[:8]}...")
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "Idempotency key conflict",
                        "message": "The provided Idempotency-Key was used for a different request",
                        "code": "idempotency_conflict"
                    }
                )

            # Return the stored response - extract the actual response from the stored data
            logger.info(f"Returning cached idempotent response for key: {idempotency_key[:8]}...")
            stored_content = stored_response["content"]
            logger.debug(f"Stored content type: {type(stored_content)}, content: {stored_content}")

            if isinstance(stored_content, dict) and "response" in stored_content:
                # Return the original response format
                logger.debug("Extracting response from stored content")
                return JSONResponse(
                    status_code=stored_response["status_code"],
                    content=stored_content["response"]
                )
            else:
                # Fallback for older format
                logger.debug("Using stored content directly (fallback)")
                return JSONResponse(
                    status_code=stored_response["status_code"],
                    content=stored_content
                )

        # Create a hash of this request for future comparison
        request_hash = self._create_request_hash(request, body)

        # Store the request hash in the request state for later use
        request.state.idempotency_key = idempotency_key
        request.state.request_hash = request_hash
        request.state.idempotency_ttl = self.ttl_seconds

        # Store idempotency information in request state for the endpoint to use
        request.state.idempotency_key = idempotency_key
        request.state.request_hash = request_hash
        request.state.idempotency_ttl = self.ttl_seconds

        # Proceed with the request - the endpoint will handle idempotency storage
        response = await call_next(request)

        return response
