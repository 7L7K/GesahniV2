"""
Authentication monitoring and structured logging.

This module provides utilities for tracking authentication events with structured logs
and Prometheus metrics for observability and alerting.
"""

import logging
import time
from contextlib import contextmanager

from .metrics import (
    AUTH_EVENT_DURATION_SECONDS,
    FINISH_CALLS_TOTAL,
    PRIVILEGED_CALLS_BLOCKED_TOTAL,
    WHOAMI_CALLS_TOTAL,
    WS_RECONNECT_ATTEMPTS_TOTAL,
)
from .telemetry import LogRecord, log_record_var, utc_now

logger = logging.getLogger(__name__)

# Track boot phase for alerting
_BOOT_START_TIME = time.time()
_BOOT_PHASE_DURATION = 30  # Consider first 30 seconds as boot phase


def _is_boot_phase() -> bool:
    """Return True if we're still in the boot phase."""
    return (time.time() - _BOOT_START_TIME) < _BOOT_PHASE_DURATION


def _get_or_create_log_record() -> LogRecord:
    """Get existing log record or create a new one."""
    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=f"auth_{int(time.time() * 1000)}")
        log_record_var.set(rec)
    return rec


def log_auth_event(
    event_type: str,
    user_id: str | None = None,
    source: str | None = None,
    jwt_status: str | None = None,
    session_ready: bool | None = None,
    is_authenticated: bool | None = None,
    lock_reason: str | None = None,
    **kwargs
) -> None:
    """
    Log an authentication event with structured data.
    
    Args:
        event_type: Type of auth event ("finish.start", "finish.end", "whoami.start", 
                    "whoami.end", "lock.on", "lock.off", "authed.change")
        user_id: User identifier
        source: Auth source ("cookie", "header", "clerk")
        jwt_status: JWT validation status ("ok", "invalid", "missing")
        session_ready: Whether session is ready
        is_authenticated: Whether user is authenticated
        lock_reason: Reason for lock events
        **kwargs: Additional fields to log
    """
    try:
        rec = _get_or_create_log_record()
        rec.auth_event_type = event_type
        rec.auth_user_id = user_id
        rec.auth_source = source
        rec.auth_jwt_status = jwt_status
        rec.auth_session_ready = session_ready
        rec.auth_is_authenticated = is_authenticated
        rec.auth_lock_reason = lock_reason
        rec.auth_boot_phase = _is_boot_phase()
        rec.timestamp = utc_now().isoformat()
        
        # Log structured event
        log_data = {
            "event": "auth_event",
            "event_type": event_type,
            "user_id": user_id,
            "source": source,
            "jwt_status": jwt_status,
            "session_ready": session_ready,
            "is_authenticated": is_authenticated,
            "lock_reason": lock_reason,
            "boot_phase": _is_boot_phase(),
            "timestamp": rec.timestamp,
            **kwargs
        }
        
        logger.info("Authentication event", extra=log_data)
        
    except Exception as e:
        logger.error(f"Failed to log auth event: {e}", exc_info=True)


@contextmanager
def track_auth_event(event_type: str, **kwargs):
    """
    Context manager to track authentication event timing.
    
    Args:
        event_type: Type of auth event
        **kwargs: Additional fields to log
    """
    start_time = time.time()
    start_kwargs = {**kwargs, "phase": "start"}
    
    try:
        log_auth_event(f"{event_type}.start", **start_kwargs)
        yield
    except Exception as e:
        # Log error event
        error_kwargs = {**kwargs, "phase": "error", "error": str(e)}
        log_auth_event(f"{event_type}.error", **error_kwargs)
        AUTH_EVENT_DURATION_SECONDS.labels(event_type=event_type, status="error").observe(
            time.time() - start_time
        )
        raise
    else:
        # Log success event
        end_kwargs = {**kwargs, "phase": "end"}
        log_auth_event(f"{event_type}.end", **end_kwargs)
        AUTH_EVENT_DURATION_SECONDS.labels(event_type=event_type, status="success").observe(
            time.time() - start_time
        )


def record_whoami_call(
    status: str,
    source: str | None = None,
    user_id: str | None = None,
    session_ready: bool | None = None,
    is_authenticated: bool | None = None,
    jwt_status: str | None = None,
) -> None:
    """Record a whoami endpoint call with metrics and logging."""
    try:
        boot_phase = "true" if _is_boot_phase() else "false"
        source_label = source or "unknown"
        
        # Increment Prometheus counter
        WHOAMI_CALLS_TOTAL.labels(
            status=status,
            source=source_label,
            boot_phase=boot_phase
        ).inc()
        
        # Log the event
        log_auth_event(
            "whoami.call",
            user_id=user_id,
            source=source,
            jwt_status=jwt_status,
            session_ready=session_ready,
            is_authenticated=is_authenticated,
            status=status,
            boot_phase=_is_boot_phase()
        )
        
    except Exception as e:
        logger.error(f"Failed to record whoami call: {e}", exc_info=True)


def record_finish_call(
    status: str,
    method: str,
    reason: str,
    user_id: str | None = None,
    set_cookie: bool | None = None,
) -> None:
    """Record an auth finish endpoint call with metrics and logging."""
    try:
        # Increment Prometheus counter
        FINISH_CALLS_TOTAL.labels(
            status=status,
            method=method,
            reason=reason
        ).inc()
        
        # Log the event
        log_auth_event(
            "finish.call",
            user_id=user_id,
            status=status,
            method=method,
            reason=reason,
            set_cookie=set_cookie
        )
        
    except Exception as e:
        logger.error(f"Failed to record finish call: {e}", exc_info=True)


def record_privileged_call_blocked(
    endpoint: str,
    reason: str,
    user_id: str | None = None,
) -> None:
    """Record a blocked privileged call."""
    try:
        # Increment Prometheus counter
        PRIVILEGED_CALLS_BLOCKED_TOTAL.labels(
            endpoint=endpoint,
            reason=reason
        ).inc()
        
        # Log the event
        log_auth_event(
            "privileged.blocked",
            user_id=user_id,
            endpoint=endpoint,
            reason=reason
        )
        
    except Exception as e:
        logger.error(f"Failed to record privileged call blocked: {e}", exc_info=True)


def record_ws_reconnect_attempt(
    endpoint: str,
    reason: str,
    user_id: str | None = None,
) -> None:
    """Record a WebSocket reconnection attempt."""
    try:
        # Increment Prometheus counter
        WS_RECONNECT_ATTEMPTS_TOTAL.labels(
            endpoint=endpoint,
            reason=reason
        ).inc()
        
        # Log the event
        log_auth_event(
            "ws.reconnect",
            user_id=user_id,
            endpoint=endpoint,
            reason=reason
        )
        
    except Exception as e:
        logger.error(f"Failed to record WS reconnect attempt: {e}", exc_info=True)


def record_auth_lock_event(
    action: str,  # "on" or "off"
    reason: str,
    user_id: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Record an authentication lock event."""
    try:
        log_auth_event(
            f"lock.{action}",
            user_id=user_id,
            lock_reason=reason,
            duration_seconds=duration_seconds
        )
        
    except Exception as e:
        logger.error(f"Failed to record auth lock event: {e}", exc_info=True)


def record_auth_state_change(
    old_state: bool,
    new_state: bool,
    user_id: str | None = None,
    source: str | None = None,
    reason: str | None = None,
) -> None:
    """Record an authentication state change."""
    try:
        log_auth_event(
            "authed.change",
            user_id=user_id,
            source=source,
            is_authenticated=new_state,
            old_authenticated=old_state,
            change_reason=reason
        )
        
    except Exception as e:
        logger.error(f"Failed to record auth state change: {e}", exc_info=True)
