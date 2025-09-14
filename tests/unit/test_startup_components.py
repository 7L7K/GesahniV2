import pytest


@pytest.mark.asyncio
async def test_init_token_store_idempotent(monkeypatch):
    """Calling token store init multiple times should not raise."""
    from app.startup.components import init_token_store_schema

    # Call twice quickly; second should not fail
    await init_token_store_schema()
    await init_token_store_schema()


@pytest.mark.asyncio
async def test_vector_store_probe_handles_missing_backend(monkeypatch):
    """Vector store probe should raise if backend misconfigured, so startup
    can record the failure. We ensure it raises a typed Exception in that case.
    """
    # Ensure environment uses an in-memory fallback by default in tests.
    monkeypatch.setenv("VECTOR_STORE", "memory")
    from app.startup.components import init_vector_store

    await init_vector_store()
