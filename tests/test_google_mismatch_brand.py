import time

import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken
from app.api import google_services


@pytest.mark.asyncio
async def test_brand_account_same_email_different_sub(tmp_path, monkeypatch):
    db = tmp_path / "tokens_google2.db"
    dao = TokenDAO(str(db))

    now = int(time.time())
    # Account A (brand) with sub-a, calendar enabled
    a = ThirdPartyToken(
        identity_id="349a63c4-0904-47f1-8cb0-a8779f97211e",
        user_id="u99",
        provider="google",
        provider_sub="sub-a",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="https://www.googleapis.com/auth/calendar.readonly",
        expires_at=now + 3600,
    )
    await dao.upsert_token(a)
    await dao.update_service_status(
        user_id="u99",
        provider="google",
        service="calendar",
        status="enabled",
        provider_sub="sub-a",
    )

    # Account B (same email string but different sub)
    b = ThirdPartyToken(
        identity_id="5b4b6024-6b7e-4af9-91ce-4d1298a1a3cc",
        user_id="u99",
        provider="google",
        provider_sub="sub-b",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        expires_at=now + 7200,
    )
    await dao.upsert_token(b)

    monkeypatch.setattr(
        google_services, "get_token", lambda user, prov: dao.get_token(user, prov)
    )
    monkeypatch.setattr(
        google_services,
        "get_all_user_tokens",
        lambda user: dao.get_all_user_tokens(user),
    )
    monkeypatch.setattr(
        google_services, "get_current_user_id", lambda request=None: "u99"
    )

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await google_services.enable_service("gmail", request=None)
    exc = ei.value
    assert isinstance(exc.detail, dict)
    assert exc.detail.get("code") == "account_mismatch"
