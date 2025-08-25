import asyncio
from app import storage


def test_dedupe_idempotency():
    storage.init_storage()
    ok1, row1 = storage.record_ledger('dedupe.test','test_skill', slots={'k':'v'}, reversible=True, idempotency_key='dedupe:1', user_id='test')
    ok2, row2 = storage.record_ledger('dedupe.test','test_skill', slots={'k':'v'}, reversible=True, idempotency_key='dedupe:1', user_id='test')
    assert ok1 is True
    assert ok2 is False
    assert row1 == row2


