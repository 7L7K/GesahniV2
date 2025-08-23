import importlib

import pytest


@pytest.mark.parametrize(
    "env,dev_mode,expect_fail",
    [
        ("prod", "0", True),
        ("production", "0", True),
        ("dev", "0", False),
        ("prod", "1", False),  # DEV_MODE overrides
    ],
)
def test_jwt_enforcement(monkeypatch, env, dev_mode, expect_fail):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("DEV_MODE", dev_mode)
    monkeypatch.setenv("JWT_SECRET", "weak")
    # force new import cycle
    if "app.main" in list(importlib.sys.modules):
        del importlib.sys.modules["app.main"]
    import app.main as m

    async def run_start():
        cm = m.lifespan(m.app)
        await cm.__aenter__()
        await cm.__aexit__(None, None, None)

    if expect_fail:
        with pytest.raises(RuntimeError):
            import asyncio

            asyncio.run(run_start())
    else:
        import asyncio

        asyncio.run(run_start())


def test_dev_warns(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("JWT_SECRET", "weak")
    if "app.main" in list(importlib.sys.modules):
        del importlib.sys.modules["app.main"]
    import asyncio

    import app.main as m

    caplog.set_level("WARNING")
    asyncio.run(m.lifespan(m.app).__aenter__())
    assert any("WEAK" in rec.message for rec in caplog.records)
