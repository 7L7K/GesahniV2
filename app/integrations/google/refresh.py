import asyncio

from ...metrics import GOOGLE_REFRESH_FAILED, GOOGLE_REFRESH_SUCCESS
from .errors import OAuthError
from .oauth import GoogleOAuth

# In-flight refresh map: key -> Future
_inflight: dict[str, asyncio.Future] = {}
_lock = asyncio.Lock()


async def refresh_dedup(user_id: str, refresh_token: str) -> tuple[bool, dict]:
    """Refresh access token with deduplication per user_id+provider.

    Returns (refreshed: bool, token_dict)
    """
    key = f"google:{user_id}"

    async with _lock:
        fut = _inflight.get(key)
        if fut is None:
            fut = asyncio.get_event_loop().create_future()
            _inflight[key] = fut
            is_initiator = True
        else:
            is_initiator = False

    if not is_initiator:
        # Wait for existing in-flight refresh
        try:
            result = await fut
            return True, result
        except Exception:
            raise

    try:
        oauth = GoogleOAuth()
        td = await oauth.refresh_access_token(refresh_token)
        # set result for waiters
        fut.set_result(td)
        try:
            GOOGLE_REFRESH_SUCCESS.labels(user_id=user_id).inc()
        except Exception:
            pass
        return True, td
    except Exception as e:
        fut.set_exception(e)
        try:
            reason = "unknown"
            if isinstance(e, OAuthError):
                reason = e.reason
            GOOGLE_REFRESH_FAILED.labels(user_id=user_id, reason=str(reason)).inc()
        except Exception:
            pass
        raise
    finally:
        async with _lock:
            _inflight.pop(key, None)
