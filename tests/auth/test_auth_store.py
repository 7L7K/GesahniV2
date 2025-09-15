import asyncio
import os
import uuid


def _rid():
    return uuid.uuid4().hex


def test_auth_store_crud(monkeypatch):
    # Isolate DB per test
    monkeypatch.setenv("AUTH_DB", os.path.abspath(".tmp_auth_test.db"))
    import app.auth_store as store

    async def _run():
        await store.ensure_tables()
        uid = _rid()
        # users
        await store.create_user(
            id=uid,
            email="a@example.com",
            password_hash=None,
            name="Alice",
            avatar_url=None,
            auth_providers=["google"],
        )
        u = await store.get_user_by_email("a@example.com")
        assert u and u["id"] == uid and u["email"] == "a@example.com"
        await store.verify_user(uid)
        # device
        did = _rid()
        await store.create_device(
            id=did, user_id=uid, device_name="Phone", ua_hash="ua", ip_hash="ip"
        )
        await store.touch_device(did)
        # session
        sid = _rid()
        await store.create_session(id=sid, user_id=uid, device_id=did, mfa_passed=True)
        await store.touch_session(sid)
        await store.revoke_session(sid)
        # oauth
        oid = _rid()
        await store.link_oauth_identity(
            id=oid,
            user_id=uid,
            provider="google",
            provider_sub="pg1",
            email_normalized="a@example.com",
        )
        # pat
        pid = _rid()
        await store.create_pat(
            id=pid,
            user_id=uid,
            name="ci",
            token_hash="th",
            scopes=["read"],
            exp_at=None,
        )
        await store.revoke_pat(pid)
        # audit
        aid = _rid()
        await store.record_audit(
            id=aid,
            user_id=uid,
            session_id=sid,
            event_type="login",
            meta={"ip": "1.2.3.4"},
        )

    asyncio.run(_run())
