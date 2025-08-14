import os
import pytest


def test_strict_vector_store_enforced(monkeypatch):
    monkeypatch.setenv("STRICT_VECTOR_STORE", "1")
    # Force a bogus backend to ensure we fail closed rather than silently fallback
    monkeypatch.setenv("VECTOR_STORE", "bogus")
    # Re-import module fresh to apply env at import time
    import importlib, sys
    sys.modules.pop("app.memory.api", None)
    with pytest.raises(Exception):
        importlib.import_module("app.memory.api")


