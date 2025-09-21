from __future__ import annotations
import logging
import os
from fastapi import Request
from typing import Any, Dict

logger = logging.getLogger(__name__)

def current_user_id_or_demo(request: Request) -> str:
    if os.getenv("DEMO_MODE") == "1":
        demo_user_id = os.getenv("DEMO_USER_ID", "00000000-0000-0000-0000-000000000001")
        logger.info(f"🎭 DEMO MODE: Using demo user ID: {demo_user_id}")
        return demo_user_id
    from app.deps.user import get_current_user_id
    return get_current_user_id(request)

def whoami_or_demo(request: Request) -> Dict[str, Any]:
    if os.getenv("DEMO_MODE") == "1":
        demo_data = {
            "id": os.getenv("DEMO_USER_ID", "00000000-0000-0000-0000-000000000001"),
            "email": os.getenv("DEMO_USER_EMAIL", "king+demo@gesahni.local"),
            "name": os.getenv("DEMO_USER_NAME", "King (Demo)"),
            "scopes": ["user:read", "music:control", "music:demo"],
            "demo": True,
        }
        logger.info(f"🎭 DEMO MODE: Returning demo whoami data: {demo_data}")
        return demo_data
    from app.auth.whoami_impl import whoami_impl
    return whoami_impl(request)
