from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from app.api.auth_password import _pwd
from app.auth import _create_session_id
from app.auth.jwt_utils import _jwt_secret as _secret_fn
from app.auth.models import RegisterOut
from app.auth_protection import public_route
from app.auth_refresh import _get_or_create_device_id
from app.cookie_config import get_token_ttls
from app.db.core import get_async_db
from app.db.models import AuthUser
from app.deps.scopes import require_scope
from app.models.user import get_user_async
from app.tokens import make_access, make_refresh
from app.user_store import user_store
from app.web.cookies import set_auth_cookies

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


@router.post(
    "/register",
    response_model=RegisterOut,
    dependencies=[Depends(require_scope("auth:register"))],
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {"access_token": "jwt", "refresh_token": "jwt"}
                    }
                }
            }
        },
        400: {"description": "ERR_INVALID or username_taken"},
    },
)
@public_route
async def register_v1(request: Request, response: Response):
    """Create a local account and return tokens."""
    # Parse body
    try:
        body = await request.json()
        username = (body.get("username") or "").strip().lower()
        password = body.get("password") or ""
    except Exception as e:
        from app.auth.errors import ERR_INVALID_JSON_PAYLOAD
        from app.http_errors import http_error

        raise http_error(
            code=ERR_INVALID_JSON_PAYLOAD, message="Invalid JSON payload", status=400
        ) from e

    # Basic validation
    if not username or len(password.strip()) < 6:
        from app.auth.errors import ERR_INVALID
        from app.http_errors import http_error

        raise http_error(
            code=ERR_INVALID,
            message="Username and password (min 6 chars) are required",
            status=400,
        )

    # Register user
    try:
        h = _pwd.hash(password)

        user = AuthUser(
            username=username,
            email=f"{username}@local.auth",
            password_hash=h,
            name=username,
            created_at=datetime.now(UTC),
        )

        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
            session.add(user)
            await session.commit()
        except IntegrityError:
            try:
                await session.rollback()
            except Exception:
                pass
            from app.errors import json_error

            return json_error(
                code="username_taken",
                message="username already exists",
                http_status=409,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"ERR_REGISTRATION_ERROR: {e}")
            raise HTTPException(status_code=500, detail="ERR_REGISTRATION_ERROR") from e
        finally:
            await session.close()
    except Exception as e:
        logger.error(f"ERR_DATABASE_ERROR: {e}")
        raise HTTPException(status_code=500, detail="ERR_DATABASE_ERROR") from e

    # Issue tokens and set cookies
    access_ttl, refresh_ttl = get_token_ttls()
    device_id = _get_or_create_device_id(request, response)

    access_token = make_access(
        {"user_id": username, "device_id": device_id}, ttl_s=access_ttl
    )

    # Create refresh with JTI
    try:
        import os as _os

        import jwt as _jwt

        int(time.time())
        jti = _jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_token = make_refresh(
            {"user_id": username, "jti": jti, "device_id": device_id}, ttl_s=refresh_ttl
        )
    except Exception:
        # Fallback minimal refresh
        jti = None
        refresh_token = make_refresh(
            {"user_id": username, "device_id": device_id}, ttl_s=refresh_ttl
        )

    # Map session id and set cookies
    try:
        payload = jwt.decode(
            access_token, _secret_fn(), algorithms=["HS256"]
        )  # ensure HS256
        at_jti = payload.get("jti")
        exp = payload.get("exp", time.time() + access_ttl)
        session_id = (
            _create_session_id(at_jti, exp)
            if at_jti
            else f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        )

        set_auth_cookies(
            response,
            access=access_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )

        # Allow refresh for this session family
        try:
            from app.deps.user import resolve_session_id
            from app.token_store import allow_refresh

            sid = resolve_session_id(request=request, user_id=username)
            if jti:
                await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"register.cookie_set_failed: {e}")

    # Update user metrics
    try:
        user = await get_user_async(username)
        if user:
            await user_store.ensure_user(user.id)
            await user_store.update_login_stats(user.id)
    except Exception:
        pass

    return {"access_token": access_token, "refresh_token": refresh_token}
