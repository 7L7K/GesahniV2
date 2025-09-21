"""
Diagnostic API endpoints for debugging and monitoring.
"""

from fastapi import APIRouter, Depends, Request
from app.deps.user import get_current_user_id
from app.auth.jwt import get_user_uuid_from_claims, get_legacy_alias_from_claims, is_uuid_sub
import jwt
from app.security.jwt_config import get_jwt_config

router = APIRouter(prefix="/v1/diag", tags=["Diagnostics"])


@router.get("/id-shape")
async def get_id_shape(request: Request):
    """
    Diagnostic endpoint to analyze JWT ID shape for client debugging.
    
    Returns information about the current user's JWT sub and alias.
    """
    try:
        # Get JWT token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return {
                "error": "No Bearer token provided",
                "sub_is_uuid": False,
                "alias_present": False
            }
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Decode JWT without verification for analysis
        try:
            config = get_jwt_config()
            claims = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        except jwt.ExpiredSignatureError:
            return {
                "error": "Token expired",
                "sub_is_uuid": False,
                "alias_present": False
            }
        except jwt.InvalidTokenError as e:
            return {
                "error": f"Invalid token: {e}",
                "sub_is_uuid": False,
                "alias_present": False
            }
        
        # Analyze the claims
        sub = claims.get("sub", "")
        alias = get_legacy_alias_from_claims(claims)
        is_uuid = is_uuid_sub(claims)
        
        # Check if sub is a valid UUID
        import uuid
        try:
            uuid.UUID(sub)
            sub_is_valid_uuid = True
        except (ValueError, TypeError):
            sub_is_valid_uuid = False
        
        return {
            "sub": sub,
            "sub_is_uuid": sub_is_valid_uuid,
            "sub_length": len(sub),
            "alias_present": alias is not None,
            "alias": alias,
            "is_uuid_only_mode": is_uuid,
            "version": claims.get("ver", 1),
            "user_id_from_claims": get_user_uuid_from_claims(claims),
            "analysis": {
                "sub_format": "UUID" if sub_is_valid_uuid else "Legacy",
                "recommendation": "Token is using UUID-only mode" if is_uuid else "Token is using legacy compatibility mode",
                "migration_status": "Complete" if is_uuid else "In progress"
            }
        }
        
    except Exception as e:
        return {
            "error": f"Analysis failed: {e}",
            "sub_is_uuid": False,
            "alias_present": False
        }


@router.get("/legacy-resolution-count")
async def get_legacy_resolution_count():
    """
    Get the current count of legacy sub resolutions.
    """
    from app.auth.jwt import get_legacy_resolution_count
    
    count = get_legacy_resolution_count()
    
    return {
        "legacy_resolution_count": count,
        "status": "healthy" if count == 0 else "warning",
        "recommendation": "No legacy resolutions detected" if count == 0 else f"{count} legacy resolutions detected - monitor for sunset planning"
    }


@router.get("/uuid-conversion-test")
async def test_uuid_conversion(user_id: str = "qazwsxppo"):
    """
    Test UUID conversion for a given user ID.
    """
    from app.util.ids import to_uuid
    
    try:
        converted_uuid = str(to_uuid(user_id))
        
        # Verify it's a valid UUID
        import uuid
        uuid.UUID(converted_uuid)
        
        return {
            "input": user_id,
            "converted_uuid": converted_uuid,
            "is_valid_uuid": True,
            "conversion_successful": True
        }
        
    except Exception as e:
        return {
            "input": user_id,
            "converted_uuid": None,
            "is_valid_uuid": False,
            "conversion_successful": False,
            "error": str(e)
        }


@router.get("/token-health")
async def get_token_health():
    """
    Get overall token health status.
    """
    from app.metrics.auth_metrics import get_metrics_summary
    
    metrics = get_metrics_summary()
    
    return {
        "token_health": {
            "legacy_resolutions": metrics["legacy_resolutions"],
            "db_coercion_failures": metrics["db_coercion_failures"],
            "overall_status": "healthy" if metrics["legacy_resolutions"]["status"] == "healthy" and metrics["db_coercion_failures"]["status"] == "healthy" else "warning"
        },
        "recommendations": [
            "Monitor legacy sub resolutions for sunset planning" if metrics["legacy_resolutions"]["total"] > 0 else "No legacy resolutions detected",
            "Investigate database coercion failures" if metrics["db_coercion_failures"]["total"] > 0 else "No database coercion failures detected"
        ]
    }
