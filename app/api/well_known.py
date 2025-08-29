from fastapi import APIRouter
import json
import os

router = APIRouter(tags=["Auth"], include_in_schema=False)


@router.get("/.well-known/jwks.json")
async def jwks():
    """Serve JWKS when JWT_PUBLIC_KEYS is configured (static).

    Expects env JWT_PUBLIC_KEYS to be a JSON object: {kid: pem, ...}. Converts to JWKS set.
    """
    try:
        data = os.getenv("JWT_PUBLIC_KEYS", "{}")
        mapping = json.loads(data)
        keys = []
        for kid, pem in mapping.items():
            # For simplicity, return x5c-less RSA/EC public keys as opaque strings under 'n' placeholder
            # Proper JWKS generation requires parsing PEM; we expose minimal compatibility for now.
            keys.append({"kid": kid, "kty": "RSA", "use": "sig", "alg": "RS256", "x5c": [pem]})
        return {"keys": keys}
    except Exception:
        return {"keys": []}

