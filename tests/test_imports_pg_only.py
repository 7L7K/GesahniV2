import importlib


def test_db_core_rejects_sqlite_urls(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///bad.db")
    with __import__("pytest").raises(RuntimeError):
        importlib.reload(__import__("app.db.core", fromlist=["*"]))


