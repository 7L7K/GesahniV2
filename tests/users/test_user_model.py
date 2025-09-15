import asyncio

from app.models import user as user_model


async def test_user_crud_cycle():
    """Test user CRUD operations using PostgreSQL."""
    # Clean up any existing test users first
    from sqlalchemy import delete

    from app.db.core import get_async_db
    from app.db.models import AuthUser

    async for session in get_async_db():
        await session.execute(delete(AuthUser).where(AuthUser.username == "alice"))
        await session.commit()

    # Use async operations
    created = await user_model.create_user_async("alice", "hashed")
    assert created.id is not None

    fetched = await user_model.get_user_async("alice")
    assert fetched.username == "alice"

    await user_model.update_login_async(fetched)
    assert fetched.login_count == 1
    assert fetched.last_login is not None

    users = await user_model.list_users_async()
    # Should have at least our test user
    alice_users = [u for u in users if u.username == "alice"]
    assert len(alice_users) == 1

    await user_model.delete_user_async(fetched)
    assert await user_model.get_user_async("alice") is None


# Wrapper to run the async test
def test_user_crud_cycle_sync():
    """Synchronous wrapper for the async test."""
    asyncio.run(test_user_crud_cycle())
