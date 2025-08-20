"""
Token creation facade module.

This module provides a clean interface for creating JWT tokens,
abstracting away the underlying implementation details.
"""

from datetime import timedelta
from typing import Optional, Dict, Any

from .auth import create_access_token, create_refresh_token


def make_access(
    claims: Dict[str, Any], 
    *, 
    ttl_s: Optional[int] = None, 
    alg: Optional[str] = None, 
    key: Optional[str] = None, 
    kid: Optional[str] = None
) -> str:
    """
    Create an access token with the given claims.
    
    Args:
        claims: Dictionary containing token claims (e.g., {"sub": "user_id"})
        ttl_s: Optional TTL in seconds (defaults to JWT_EXPIRE_MINUTES)
        alg: Optional algorithm override (currently ignored, uses HS256)
        key: Optional key override (currently ignored, uses JWT_SECRET)
        kid: Optional key ID (currently ignored)
    
    Returns:
        JWT access token string
    """
    # Convert ttl_s to timedelta if provided
    expires_delta = None
    if ttl_s is not None:
        expires_delta = timedelta(seconds=ttl_s)
    
    # For now, just call the existing implementation
    # TODO: In future steps, this will be refactored to use the new implementation
    return create_access_token(claims, expires_delta=expires_delta)


def make_refresh(
    claims: Dict[str, Any], 
    *, 
    ttl_s: Optional[int] = None, 
    alg: Optional[str] = None, 
    key: Optional[str] = None, 
    kid: Optional[str] = None
) -> str:
    """
    Create a refresh token with the given claims.
    
    Args:
        claims: Dictionary containing token claims (e.g., {"sub": "user_id"})
        ttl_s: Optional TTL in seconds (defaults to JWT_REFRESH_EXPIRE_MINUTES)
        alg: Optional algorithm override (currently ignored, uses HS256)
        key: Optional key override (currently ignored, uses JWT_SECRET)
        kid: Optional key ID (currently ignored)
    
    Returns:
        JWT refresh token string
    """
    # Convert ttl_s to timedelta if provided
    expires_delta = None
    if ttl_s is not None:
        expires_delta = timedelta(seconds=ttl_s)
    
    # For now, just call the existing implementation
    # TODO: In future steps, this will be refactored to use the new implementation
    return create_refresh_token(claims, expires_delta=expires_delta)
