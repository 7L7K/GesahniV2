#!/usr/bin/env python3
"""
Debug script to test login functionality step by step
"""

import asyncio
import json
import sys

# Add current directory to path
sys.path.append(".")


async def debug_login():
    print("=== Login Debug Script ===")

    try:
        # Test token creation
        print("\n1. Testing token creation...")
        from uuid import uuid4

        from app.tokens import make_access, make_refresh

        access_token = make_access({"user_id": "demo"})
        refresh_jti = uuid4().hex
        refresh_token = make_refresh({"user_id": "demo", "jti": refresh_jti})

        print(f"✓ Access token created (length: {len(access_token)})")
        print(f"✓ Refresh token created (length: {len(refresh_token)})")

        # Test user store operations
        print("\n2. Testing user store operations...")
        from app.user_store import user_store

        await user_store.ensure_user("demo")
        await user_store.increment_login("demo")
        stats = await user_store.get_stats("demo") or {}
        print(f"✓ User store operations completed: {stats}")

        # Test cookie configuration
        print("\n3. Testing cookie configuration...")

        # Create a mock request/response
        class MockRequest:
            def __init__(self):
                self.cookies = {}
                self.headers = {"User-Agent": "test", "X-Forwarded-For": "127.0.0.1"}

        class MockResponse:
            def __init__(self):
                self.headers = {}
                self.cookies_set = []

            def set_cookie(self, key, value, **kwargs):
                self.cookies_set.append((key, value, kwargs))

        request = MockRequest()
        response = MockResponse()

        from app.cookie_config import get_cookie_config, get_token_ttls
        from app.web.cookies import set_auth_cookies

        cookie_config = get_cookie_config(request)
        access_ttl, refresh_ttl = get_token_ttls()

        print(f"✓ Cookie config: {cookie_config}")
        print(f"✓ Token TTLs: access={access_ttl}, refresh={refresh_ttl}")

        # Test session creation
        print("\n4. Testing session creation...")
        from app.api.auth import _jwt_secret
        from app.security import _jwt_decode
        from app.session_store import get_session_store

        store = get_session_store()

        # Decode access token to get JTI
        secret = _jwt_secret()
        payload = _jwt_decode(access_token, secret, algorithms=["HS256"])
        jti = payload.get("jti")
        expires_at = payload.get("exp", 0)

        if jti:
            session_id = store.create_session(jti, expires_at)
            print(f"✓ Session created: {session_id}")
        else:
            print("⚠ No JTI in access token")

        # Test setting cookies
        print("\n5. Testing cookie setting...")
        set_auth_cookies(
            response,
            access=access_token,
            refresh=refresh_token,
            session_id=session_id or f"sess_{0}_{0:08x}",
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )
        print(f"✓ Cookies set: {len(response.cookies_set)} cookies")

        print("\n=== All tests passed! ===")
        print("\nExpected response structure:")
        expected_response = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token": access_token,
            "stats": stats,
        }
        print(json.dumps(expected_response, indent=2))

    except Exception as e:
        print(f"\n❌ Error at step: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_login())
