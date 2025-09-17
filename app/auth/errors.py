"""Authentication error code constants.

These constants prevent typos in error codes and make it easy for grep to find all usages.
"""

from __future__ import annotations

# CSRF-related errors
ERR_MISSING_CSRF = "missing_csrf"
ERR_INVALID_CSRF = "invalid_csrf"

# Intent header errors
ERR_MISSING_INTENT = "missing_intent_header_cross_site"

# Rate limiting errors
ERR_TOO_MANY = "too_many_requests"

# Token-related errors
ERR_INVALID_REFRESH = "invalid_refresh"
ERR_TOKEN_GEN_FAILED = "token_generation_failed"
ERR_TOKEN_VALIDATION_FAILED = "token_validation_failed"

# Additional auth error codes
ERR_DEV_TOKEN_DISABLED = "dev_token_disabled"
ERR_MISSING_JWT_SECRET = "missing_jwt_secret"
ERR_INSECURE_JWT_SECRET = "insecure_jwt_secret"
ERR_MISSING_USERNAME = "missing_username"
ERR_TOKEN_ISSUE_FAILED = "token_issue_failed"

# Registration-specific errors
ERR_INVALID_JSON_PAYLOAD = "invalid_json_payload"
ERR_INVALID = "invalid"
ERR_REGISTRATION_ERROR = "registration_error"
ERR_DATABASE_ERROR = "database_error"

# Service-specific errors
ERR_CANNOT_MINT_TOKEN_FOR_INVALID_USER = "cannot_mint_token_for_invalid_user"

# General errors
ERR_NOT_FOUND = "not_found"
