#!/usr/bin/env python3
"""
Simple test script to verify upsert hardening changes.
"""

import asyncio
import os
import time

from app.auth_store_tokens import upsert_token
from app.models.third_party_tokens import ThirdPartyToken

# Disable strict contracts for testing
os.environ["STRICT_CONTRACTS"] = "false"


async def test_provider_sub_priority():
    """Test that provider_sub is prioritized from new values."""
    print("Testing provider_sub priority...")

    # Create a token without provider_sub
    token1 = ThirdPartyToken(
        id="test_token_1",
        user_id="test_user_1",
        identity_id="test_identity_1",
        provider="google",
        provider_iss="https://accounts.google.com",
        provider_sub=None,
        access_token="test_access_token_" + "X" * 20,
        refresh_token="test_refresh_token_" + "Y" * 20,
        expires_at=int(time.time()) + 3600,
        scopes="email profile",
        created_at=int(time.time()),
        updated_at=int(time.time()),
        is_valid=True,
    )

    # Upsert first token
    result1 = await upsert_token(token1)
    print(f"First upsert result: {result1}")

    # Create another token with provider_sub for same user/provider
    token2 = ThirdPartyToken(
        id="test_token_2",
        user_id="test_user_1",
        identity_id="test_identity_1",
        provider="google",
        provider_iss="https://accounts.google.com",
        provider_sub="google_sub_123",
        access_token="test_access_token_" + "Z" * 20,
        refresh_token="test_refresh_token_" + "W" * 20,
        expires_at=int(time.time()) + 7200,
        scopes="email profile calendar",
        created_at=int(time.time()),
        updated_at=int(time.time()),
        is_valid=True,
    )

    # Upsert second token - should update provider_sub
    result2 = await upsert_token(token2)
    print(f"Second upsert result: {result2}")

    # Verify the token has the new provider_sub
    from app.auth_store_tokens import get_token

    retrieved = await get_token("test_user_1", "google")
    if retrieved and retrieved.provider_sub == "google_sub_123":
        print("✓ provider_sub correctly updated to new value")
    else:
        print(
            f"✗ provider_sub not updated correctly. Got: {retrieved.provider_sub if retrieved else None}"
        )


async def main():
    await test_provider_sub_priority()


if __name__ == "__main__":
    asyncio.run(main())
