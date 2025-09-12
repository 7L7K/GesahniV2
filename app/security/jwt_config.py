import json
import os
import re
from dataclasses import dataclass

_PLACEHOLDER_PAT = re.compile(r"your[-_ ]secure[-_ ]jwt[-_ ]secret|placeholder|changeme", re.I)

@dataclass(frozen=True)
class JWTConfig:
    alg: str                 # "HS256" | "RS256" | "ES256"
    secret: str | None       # HS256 only
    private_keys: dict[str, str] | None  # kid -> PEM
    public_keys: dict[str, str] | None   # kid -> PEM
    issuer: str | None
    audience: str | None
    access_ttl_min: int
    refresh_ttl_min: int
    clock_skew_s: int

def _parse_json_env(name: str) -> dict[str, str] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError(f"{name} must be a JSON object mapping kid->PEM")
        return {str(k): str(v) for k, v in obj.items()}
    except Exception as e:
        raise RuntimeError(f"Invalid JSON in {name}: {e}") from e

def _require_strong_secret(secret: str, *, allow_dev: bool) -> None:
    # In dev/test modes, allow shorter secrets to support unit/integration tests
    if not allow_dev and len(secret) < 32:
        raise RuntimeError("JWT_SECRET too short (<32 chars).")
    if not allow_dev and _PLACEHOLDER_PAT.search(secret):
        raise RuntimeError("JWT_SECRET contains placeholder text; replace immediately.")
    if not allow_dev and re.fullmatch(r"(dev|staging|prod|test|secret|token)[-_]?\d*", secret, re.I):
        raise RuntimeError("JWT_SECRET looks like a low-entropy label; use a random value.")

def get_jwt_config(*, allow_dev_weak=None) -> JWTConfig:
    # Auto-detect DEV/TEST modes if not explicitly specified
    if allow_dev_weak is None:
        dev = os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
        test = (os.getenv("ENV", "").strip().lower() == "test") or (
            os.getenv("PYTEST_RUNNING") or os.getenv("PYTEST_CURRENT_TEST")
        )
        allow_dev_weak = bool(dev or test)
    algs = [a.strip().upper() for a in os.getenv("JWT_ALGS", "HS256").split(",") if a.strip()]
    if not algs:
        algs = ["HS256"]
    alg = algs[0]

    issuer = os.getenv("JWT_ISS") or None
    audience = os.getenv("JWT_AUD") or None
    access_ttl_min = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
    refresh_ttl_min = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
    clock_skew_s = int(os.getenv("JWT_CLOCK_SKEW_S", os.getenv("JWT_LEEWAY", "60")))

    priv = _parse_json_env("JWT_PRIVATE_KEYS")
    pub  = _parse_json_env("JWT_PUBLIC_KEYS")

    # Support legacy JWT_SECRET for HS256
    if alg == "HS256":
        secret = os.getenv("JWT_SECRET", "")
        if not secret and not priv:
            raise RuntimeError("JWT_SECRET missing for HS256 (or use JWT_PRIVATE_KEYS for rotation).")
        if secret and not priv:
            # Legacy mode: single HS256 secret
            _require_strong_secret(secret, allow_dev=allow_dev_weak)
            return JWTConfig(alg="HS256", secret=secret, private_keys=None, public_keys=None,
                             issuer=issuer, audience=audience,
                             access_ttl_min=access_ttl_min, refresh_ttl_min=refresh_ttl_min,
                             clock_skew_s=clock_skew_s)
        elif priv and pub:
            # HS256 with key rotation support
            if secret:
                raise RuntimeError("Cannot specify both JWT_SECRET and JWT_PRIVATE_KEYS for HS256.")
            missing = sorted(set(priv.keys()) - set(pub.keys()))
            if missing:
                raise RuntimeError(f"Public key(s) missing for kid(s): {', '.join(missing)}")
            return JWTConfig(alg="HS256", secret=None, private_keys=priv, public_keys=pub,
                             issuer=issuer, audience=audience,
                             access_ttl_min=access_ttl_min, refresh_ttl_min=refresh_ttl_min,
                             clock_skew_s=clock_skew_s)
        else:
            raise RuntimeError("Invalid HS256 configuration: specify JWT_SECRET or JWT_PRIVATE_KEYS/JWT_PUBLIC_KEYS.")

    if alg in ("RS256", "ES256"):
        if not (priv and pub):
            raise RuntimeError(f"{alg} requires JWT_PRIVATE_KEYS and JWT_PUBLIC_KEYS JSON (kid->PEM).")
        missing = sorted(set(priv.keys()) - set(pub.keys()))
        if missing:
            raise RuntimeError(f"Public key(s) missing for kid(s): {', '.join(missing)}")
        return JWTConfig(alg=alg, secret=None, private_keys=priv, public_keys=pub,
                         issuer=issuer, audience=audience,
                         access_ttl_min=access_ttl_min, refresh_ttl_min=refresh_ttl_min,
                         clock_skew_s=clock_skew_s)

    raise RuntimeError(f"Unsupported JWT_ALGS value: {alg}")
