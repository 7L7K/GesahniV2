import pytest


def test_strict_vector_store_enforced(monkeypatch):
    monkeypatch.setenv("STRICT_VECTOR_STORE", "1")
    # Force a bogus DSN to ensure we fail closed rather than silently fallback
    monkeypatch.setenv("VECTOR_DSN", "bogus://invalid")
    # Re-import module fresh to apply env at import time
    import importlib
    import sys

    # Clear modules to force fresh import
    modules_to_clear = [k for k in sys.modules.keys() if k.startswith("app.memory")]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)

    with pytest.raises(ValueError, match="Unsupported vector store scheme"):
        importlib.import_module("app.memory.unified_store").create_vector_store()
