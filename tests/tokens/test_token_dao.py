import time

import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
async def test_upsert_unions_scopes_and_invalidates_prev(tmp_path):
    db = tmp_path / "tokens.db"
    dao = TokenDAO(str(db))

    now = int(time.time())
    t1 = ThirdPartyToken(
        identity_id="ec686d62-0dc6-45bf-89cb-eeb970501162",
        user_id="u1",
        provider="google",
        provider_sub="sub-a",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="gmail",
        expires_at=now + 3600,
        created_at=now,
        updated_at=now,
    )

    ok = await dao.upsert_token(t1)
    assert ok

    # Upsert with additional scope
    time.sleep(0.01)
    t2 = ThirdPartyToken(
        identity_id="70fb00c0-4ae7-45fc-a9a9-ce750c479376",
        user_id="u1",
        provider="google",
        provider_sub="sub-a",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="calendar",
        expires_at=now + 7200,
    )
    ok = await dao.upsert_token(t2)
    assert ok

    # Latest valid token should have unioned scopes
    latest = await dao.get_token("u1", "google")
    assert latest is not None
    scopes = set((latest.scope or "").split())
    assert "gmail" in scopes and "calendar" in scopes

    # There should be only one valid token returned
    all_valid = await dao.get_all_user_tokens("u1")
    assert len(all_valid) == 1
