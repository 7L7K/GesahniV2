# JWT utility functions to avoid circular imports


def _payload_scopes(payload: dict | None) -> set[str]:
    """Extract scopes from JWT payload."""
    if not isinstance(payload, dict):
        return set()
    scopes = payload.get("scope") or payload.get("scopes") or []
    if isinstance(scopes, str):
        return set(scopes.split())
    elif isinstance(scopes, list):
        return set(str(s) for s in scopes)
    return set()
