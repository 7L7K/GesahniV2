# Security module package

from .jwt_config import get_jwt_config, JWTConfig

# Import jwt_decode from the main security module (app.security)
try:
    from .security import jwt_decode, decode_jwt, get_rate_limit_snapshot, _get_request_payload, verify_token
except ImportError:
    # Fallback for circular import situations
    jwt_decode = None
    decode_jwt = None
    get_rate_limit_snapshot = None
    _get_request_payload = None
    verify_token = None

__all__ = ["get_jwt_config", "JWTConfig", "jwt_decode", "decode_jwt", "get_rate_limit_snapshot", "_get_request_payload", "verify_token"]
