"""JWT utilities for GesahniV2 authentication."""

import json
import logging
import os

import jwt
from fastapi import HTTPException

from ..security import jwt_decode

logger = logging.getLogger(__name__)


def _in_test_mode() -> bool:
    """Check if running in test mode."""

    def v(s):
        return str(os.getenv(s, "")).strip().lower()

    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING", "").strip().lower() in {"1", "true", "yes", "on"}
        or v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("ENV") == "test"
    )


def _decode_any(token: str) -> dict | None:
    """Decode any application JWT, supporting key rotation."""
    if not token:
        return None

    # Prefer the centralized decoder which is rotation-aware.
    try:
        from ..tokens import decode_jwt_token as _decode_jwt_token

        return _decode_jwt_token(token)
    except jwt.InvalidTokenError as e:
        logger.warning(
            "JWT decode failed via centralized decoder: %s", e, exc_info=False
        )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Unexpected error in centralized JWT decode: %s", e, exc_info=True)

    # Fallback to legacy HS256 secret when available for backward compatibility.
    try:
        secret = _jwt_secret()
    except HTTPException:
        secret = None
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Failed to obtain JWT secret: %s", e, exc_info=True)
        secret = None

    if not secret:
        return None

    try:
        return jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.DecodeError) as e:
        logger.warning("JWT decode failed with legacy secret: %s", e, exc_info=False)
        return None
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Unexpected error in legacy JWT decode: %s", e, exc_info=True)
        return None


def _jwt_secret() -> str:
    from app.http_errors import http_error

    sec = os.getenv("JWT_SECRET")
    if not sec or sec.strip() == "":
        raise http_error(
            code="ERR_MISSING_JWT_SECRET", message="JWT secret is missing", status=500
        )
    # Do not automatically allow weaker secrets for test mode here; only
    # allow an explicit DEV_MODE bypass below. This avoids silently relaxing
    # checks during unit tests and keeps security checks strict by default.
    # Allow DEV_MODE to relax strength checks (explicit opt-in)
    try:
        dev_mode = str(os.getenv("DEV_MODE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        # Only allow DEV_MODE bypass when NOT running tests. Tests should still
        # exercise the strict secret validation unless they explicitly opt-in.
        if dev_mode and not _in_test_mode():
            try:
                logging.getLogger(__name__).warning(
                    "Using weak JWT_SECRET because DEV_MODE=1 is set. Do NOT use in production."
                )
            except Exception:
                # Continue even if logging fails
                pass
            return sec
    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Error processing DEV_MODE environment variable: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error in JWT secret validation: {type(e).__name__}: {e}"
        )
    # Security check: prevent use of default/placeholder secrets
    # Allow "secret" for test compatibility
    insecure_secrets = {"change-me", "default", "placeholder", "key"}
    if sec.strip().lower() == "secret":
        insecure_secrets.discard("secret")
    if sec.strip().lower() in insecure_secrets:
        from app.http_errors import http_error

        raise http_error(
            code="ERR_INSECURE_JWT_SECRET", message="JWT secret is insecure", status=500
        )
    return sec


def _key_pool_from_env() -> dict[str, str]:
    raw = os.getenv("JWT_KEYS") or os.getenv("JWT_KEY_POOL")
    if raw is not None and str(raw).strip() == "":
        raw = None
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj:
                return {str(k): str(v) for k, v in obj.items()}
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse JWT_KEYS as JSON: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error parsing JWT key pool: {type(e).__name__}: {e}"
            )
        try:
            items = [p.strip() for p in str(raw).split(",") if p.strip()]
            out: dict[str, str] = {}
            for it in items:
                if ":" in it:
                    kid, sec = it.split(":", 1)
                    out[kid.strip()] = sec.strip()
            if out:
                return out
        except (ValueError, AttributeError, IndexError) as e:
            logger.warning(f"Failed to parse JWT_KEYS as colon-separated values: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error parsing JWT key pool fallback: {type(e).__name__}: {e}"
            )
    sec = os.getenv("JWT_SECRET")
    if not sec or sec.strip() == "":
        from app.http_errors import http_error

        raise http_error(
            code="ERR_MISSING_JWT_SECRET", message="JWT secret is missing", status=500
        )
    # Security check: prevent use of default/placeholder secrets
    # Allow "secret" during testing for test compatibility
    insecure_secrets = {"change-me", "default", "placeholder", "key"}
    if _in_test_mode() or sec.strip().lower() == "secret":
        # Allow "secret" for tests and explicit test usage
        insecure_secrets.discard("secret")
    if sec.strip().lower() in insecure_secrets:
        from app.http_errors import http_error

        raise http_error(
            code="ERR_INSECURE_JWT_SECRET", message="JWT secret is insecure", status=500
        )
    return {"k0": sec}


def _primary_kid_secret() -> tuple[str, str]:
    pool = _key_pool_from_env()
    if not pool:
        from app.http_errors import http_error

        raise http_error(
            code="ERR_MISSING_JWT_SECRET", message="JWT secret is missing", status=500
        )
    kid, sec = next(iter(pool.items()))
    return kid, sec


def _decode_any_strict(token: str, *, leeway: int = 0) -> dict:
    pool = _key_pool_from_env()
    if not pool:
        from app.http_errors import http_error

        raise http_error(
            code="ERR_MISSING_JWT_SECRET", message="JWT secret is missing", status=500
        )
    try:
        hdr = jwt.get_unverified_header(token)
        kid = hdr.get("kid")
    except Exception:
        kid = None
    keys = list(pool.items())
    if kid and kid in pool:
        keys = [(kid, pool[kid])] + [(k, s) for (k, s) in pool.items() if k != kid]
    elif kid and kid not in pool:
        try:
            logger.info("auth.jwt kid_not_found attempting_pool_refresh")
        except Exception:
            pass
    last_err: Exception | None = None
    for _, sec in keys:
        try:
            return jwt_decode(token, sec, algorithms=["HS256"], leeway=leeway)
        except Exception as e:
            last_err = e
            continue
    if isinstance(last_err, jwt.ExpiredSignatureError):
        raise last_err
    from ..http_errors import unauthorized

    raise unauthorized(
        message="authentication required", hint="login or include Authorization header"
    )
