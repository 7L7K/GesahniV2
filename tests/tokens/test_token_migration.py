import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
async def test_token_upsert_with_postgresql():
    """Test token upsert operations using PostgreSQL."""

    dao = TokenDAO()

    token = ThirdPartyToken(
        identity_id="0cc892cd-1663-405f-a30f-136c720e0846",
        user_id="testuser",
        provider="google",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="openid email",
        expires_at=9999999999,
        created_at=1,
        updated_at=1,
    )

    # Should return True, inserting/updating the token
    ok = await dao.upsert_token(token)
    assert ok is True

    # Verify the token can be retrieved
    from app.db.core import get_async_db
    from app.db.models import ThirdPartyToken as DBToken

    async with get_async_db() as session:
        from sqlalchemy import select

        stmt = select(DBToken).where(
            DBToken.user_id == "testuser", DBToken.provider == "google"
        )
        result = await session.execute(stmt)
        stored_token = result.scalar_one_or_none()

        assert stored_token is not None
        assert stored_token.user_id == "testuser"
        assert stored_token.provider == "google"
