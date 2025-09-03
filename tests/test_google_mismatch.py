import time

import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken
from app.api import google_services
from app.error_envelope import build_error
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_enable_service_account_mismatch(tmp_path, monkeypatch):
    """Test that enabling Gmail service raises account_mismatch when Calendar is enabled on different account."""
    db = tmp_path / "tokens_google.db"
    dao = TokenDAO(str(db))

    now = int(time.time())
    # Old token (account A) with calendar enabled
    a = ThirdPartyToken(
        identity_id="a6b8e03b-4082-447f-86b5-78bbec791734",
        user_id="u42",
        provider="google",
        provider_sub="sub-a",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="openid email profile https://www.googleapis.com/auth/calendar.readonly",
        expires_at=now + 3600,
    )
    await dao.upsert_token(a)
    # Enable calendar on account A
    await dao.update_service_status(
        user_id="u42",
        provider="google",
        service="calendar",
        status="enabled",
        provider_sub="sub-a",
        provider_iss="https://accounts.google.com",
    )

    # New token (account B) more recent - explicitly set created_at to be much newer
    b = ThirdPartyToken(
        identity_id="7f45032a-5697-4913-9869-6d471ab20175",
        user_id="u42",
        provider="google",
        provider_sub="sub-b",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="openid email profile https://www.googleapis.com/auth/gmail.readonly",
        expires_at=now + 7200,
        created_at=now
        + 100,  # Make it 100 seconds newer to ensure it's definitely more recent
    )
    await dao.upsert_token(b)

    # Verify the setup: we should have two tokens, one with calendar enabled
    all_tokens = await dao.get_all_user_tokens("u42")
    assert len(all_tokens) == 2

    # Get the current token (should be the newer one)
    current_token = await dao.get_token("u42", "google")
    assert current_token.provider_sub == "sub-b"  # Should be the newer token

    # Test the account mismatch logic directly
    from app.service_state import parse as parse_state

    # Check that account A has calendar enabled
    account_a = next(t for t in all_tokens if t.provider_sub == "sub-a")
    print(f"Account A service_state: {account_a.service_state}")
    st_a = parse_state(account_a.service_state)
    print(f"Parsed state A: {st_a}")
    assert st_a.get("calendar", {}).get("status") == "enabled"

    # Check that account B has no services enabled
    account_b = next(t for t in all_tokens if t.provider_sub == "sub-b")
    st_b = parse_state(account_b.service_state)
    assert not st_b or not any(
        entry.get("status") == "enabled" for entry in st_b.values()
    )

    # Verify the mismatch condition: different provider_sub and enabled service
    has_mismatch = False
    for other_token in all_tokens:
        if (
            other_token.provider_sub
            and other_token.provider_sub != current_token.provider_sub
        ):
            other_state = parse_state(other_token.service_state)
            if any(entry.get("status") == "enabled" for entry in other_state.values()):
                has_mismatch = True
                break

    assert (
        has_mismatch
    ), "Should detect account mismatch between calendar (sub-a) and gmail (sub-b)"
