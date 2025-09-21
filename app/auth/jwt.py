"""
JWT Claims Building and Management

This module provides centralized JWT claims building with UUID-only sub claims
and optional alias support for migration analytics.
"""

import uuid
from typing import Any, Dict, Optional
from app.util.ids import to_uuid


def build_claims(user_id: str, alias: Optional[str] = None) -> Dict[str, Any]:
    """
    Build JWT claims with UUID-only sub and optional alias for migration analytics.
    
    Args:
        user_id: User identifier (legacy username or UUID)
        alias: Optional alias for migration analytics (typically the original username)
        
    Returns:
        Dictionary containing JWT claims with UUID sub and optional alias
        
    Raises:
        ValueError: If user_id cannot be converted to UUID
    """
    # Convert user_id to UUID (handles both legacy usernames and existing UUIDs)
    user_uuid = to_uuid(user_id)
    uuid_str = str(user_uuid)
    
    # Build base claims with UUID-only sub
    claims = {
        "sub": uuid_str,
        "ver": 2,  # Version 2 indicates UUID-only sub
    }
    
    # Add alias for migration analytics if provided
    if alias:
        claims["alias"] = alias
    
    return claims


def build_claims_with_legacy_support(user_id: str, alias: Optional[str] = None) -> Dict[str, Any]:
    """
    Build JWT claims with legacy sub support for backward compatibility.
    
    This function is used during the transition period to maintain compatibility
    with existing tokens while new tokens use UUID-only sub claims.
    
    Args:
        user_id: User identifier (legacy username or UUID)
        alias: Optional alias for migration analytics
        
    Returns:
        Dictionary containing JWT claims with both sub and user_id for compatibility
    """
    # Convert user_id to UUID
    user_uuid = to_uuid(user_id)
    uuid_str = str(user_uuid)
    
    # Build claims with both sub (UUID) and user_id (legacy) for compatibility
    claims = {
        "sub": uuid_str,
        "user_id": user_id,  # Keep original for backward compatibility
        "ver": 1,  # Version 1 indicates legacy compatibility mode
    }
    
    # Add alias for migration analytics if provided
    if alias:
        claims["alias"] = alias
    
    return claims


def is_uuid_sub(claims: Dict[str, Any]) -> bool:
    """
    Check if JWT claims use UUID-only sub (version 2).
    
    Args:
        claims: JWT claims dictionary
        
    Returns:
        True if claims use UUID-only sub, False otherwise
    """
    version = claims.get("ver", 1)
    return version >= 2


def get_user_uuid_from_claims(claims: Dict[str, Any]) -> str:
    """
    Extract user UUID from JWT claims, handling both legacy and UUID-only formats.
    
    Args:
        claims: JWT claims dictionary
        
    Returns:
        User UUID as string
    """
    # For version 2+ (UUID-only), sub is always the UUID
    if is_uuid_sub(claims):
        return claims.get("sub", "")
    
    # For version 1 (legacy), sub might be legacy username, so use user_id or convert sub
    sub = claims.get("sub", "")
    user_id = claims.get("user_id", "")
    
    # If sub is a UUID, use it directly
    try:
        uuid.UUID(sub)
        return sub
    except (ValueError, TypeError):
        pass
    
    # Otherwise, convert user_id to UUID
    if user_id:
        return str(to_uuid(user_id))
    
    # Fallback: convert sub to UUID
    return str(to_uuid(sub))


def get_legacy_alias_from_claims(claims: Dict[str, Any]) -> Optional[str]:
    """
    Extract legacy alias from JWT claims for migration analytics.
    
    Args:
        claims: JWT claims dictionary
        
    Returns:
        Legacy alias if present, None otherwise
    """
    # Check for explicit alias field
    if "alias" in claims:
        return claims["alias"]
    
    # For legacy tokens, user_id might be the original username
    if not is_uuid_sub(claims):
        user_id = claims.get("user_id", "")
        sub = claims.get("sub", "")
        
        # If user_id looks like a legacy username, use it as alias
        if user_id and len(user_id) <= 12 and not _is_uuid_format(user_id):
            return user_id
        
        # If sub looks like a legacy username, use it as alias
        if sub and len(sub) <= 12 and not _is_uuid_format(sub):
            return sub
    
    return None


def _is_uuid_format(value: str) -> bool:
    """Check if a string is in UUID format."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


# Metrics tracking for legacy sub resolutions
_legacy_resolution_count = 0


def track_legacy_resolution(source: str, original_sub: str, resolved_uuid: str) -> None:
    """
    Track legacy sub resolution for monitoring and sunset planning.
    
    Args:
        source: Source of the legacy sub ("alias" or "username")
        original_sub: Original legacy sub value
        resolved_uuid: Resolved UUID value
    """
    global _legacy_resolution_count
    _legacy_resolution_count += 1
    
    # Log structured warning for monitoring
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        "legacy_sub_mapped",
        extra={
            "event": "legacy_sub_mapped",
            "source": source,
            "original_sub": original_sub,
            "resolved_uuid": resolved_uuid,
            "resolution_count": _legacy_resolution_count,
        }
    )


def get_legacy_resolution_count() -> int:
    """Get the total count of legacy sub resolutions."""
    return _legacy_resolution_count
