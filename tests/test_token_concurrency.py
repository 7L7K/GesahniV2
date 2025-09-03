import asyncio
import time

import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
async def test_concurrent_upserts_union_scopes(tmp_path):
    db = tmp_path / "tokens_conc.db"
    dao = TokenDAO(str(db))

    now = int(time.time())
    base = ThirdPartyToken(identity_id="852f19fd-bd5e-4e57-a5cd-8201343a6af7", 
        user_id="u777",
        provider="google",
        provider_sub="sub-conc",
        provider_iss="https://accounts.google.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="gmail",
        expires_at=now + 3600,
    )
    await dao.upsert_token(base)

    async def upsert_with_scope(suffix: str):
        t = ThirdPartyToken(identity_id="b0e0d486-eb72-4320-b2a7-a1565c3c619a", 
            user_id="u777",
            provider="google",
            provider_sub="sub-conc",
            provider_iss="https://accounts.google.com",
            access_token=f"at-{suffix}",
            refresh_token=f"rt-{suffix}",
            scopes=suffix,
            expires_at=now + 3600,
        )
        return await dao.upsert_token(t)

    # Run concurrent upserts adding different scopes
    tasks = [upsert_with_scope("calendar"), upsert_with_scope("drive"), upsert_with_scope("gmail")]
    res = await asyncio.gather(*tasks)
    assert all(res)

    latest = await dao.get_token("u777", "google", "sub-conc")
    assert latest is not None
    scopes = set((latest.scope or "").split())
    assert {"gmail", "calendar", "drive"}.issubset(scopes)

