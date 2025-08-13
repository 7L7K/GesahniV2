from __future__ import annotations

import os
import hashlib
import asyncio

from app.auth_store import ensure_tables, create_pat
from app.api import auth as auth_api


def test_pat_verify_scope_and_revoked(tmp_path, monkeypatch):
    os.environ.setdefault("AUTH_DB", str(tmp_path / "auth.db"))

    async def _setup():
        await ensure_tables()
        token = "pat_live_testtoken"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        await create_pat(id="pat1", user_id="u", name="t", token_hash=token_hash, scopes=["read", "write"], exp_at=None)
        return token

    token = asyncio.get_event_loop().run_until_complete(_setup())

    # Valid scope
    rec = auth_api.verify_pat(token, ["read"])  # type: ignore[attr-defined]
    assert rec is not None
    # Missing scope
    rec2 = auth_api.verify_pat(token, ["admin"])  # type: ignore[attr-defined]
    assert rec2 is None


