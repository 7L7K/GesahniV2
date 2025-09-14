import logging
import os

log = logging.getLogger(__name__)


def run_config_validation() -> None:
    """Validate critical auth/cookie/CORS configuration at startup.

    Logs warnings or errors; does not raise to avoid crashing dev. In prod, emits
    clear errors when JWT secrets are missing or cookie security is misconfigured.
    """
    env = os.getenv("ENV", "dev").lower()
    is_prod = env in {"prod", "production"}

    problems: list[dict] = []

    # JWT secret required in prod for HS tokens
    if is_prod and not (os.getenv("JWT_SECRET") or os.getenv("JWT_PRIVATE_KEYS")):
        problems.append(
            {
                "code": "missing_jwt_secret",
                "message": "JWT secret or private keys required in production",
                "hint": "set JWT_SECRET or JWT_PRIVATE_KEYS",
            }
        )

    # SameSite=None requires Secure
    samesite = (os.getenv("COOKIE_SAMESITE") or "lax").lower()
    secure = (os.getenv("COOKIE_SECURE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if samesite == "none" and not secure:
        problems.append(
            {
                "code": "samesite_without_secure",
                "message": "COOKIE_SAMESITE=None requires COOKIE_SECURE=true",
                "hint": "enable Secure cookies when using SameSite=None",
            }
        )

    # CORS with credentials
    creds = (os.getenv("CORS_ALLOW_CREDENTIALS") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not creds:
        problems.append(
            {
                "code": "cors_no_credentials",
                "message": "CORS_ALLOW_CREDENTIALS=false with cookie auth may break browsers",
                "hint": "set CORS_ALLOW_CREDENTIALS=1 when using cookie-based auth",
            }
        )

    # Host cookie prefix safety
    if secure and (
        os.getenv("USE_HOST_COOKIE_PREFIX", "1").lower()
        not in {"1", "true", "yes", "on"}
    ):
        problems.append(
            {
                "code": "host_prefix_disabled",
                "message": "__Host- cookie prefix disabled while Secure=true",
                "hint": "set USE_HOST_COOKIE_PREFIX=1 for stronger cookie scoping",
            }
        )

    # Emit structured error and fail fast in production on critical combos
    if problems:
        payload = {"ok": False, "problems": problems}
        if is_prod:
            raise RuntimeError(str(payload))
        else:
            log.warning("config.validation", extra={"meta": payload})
