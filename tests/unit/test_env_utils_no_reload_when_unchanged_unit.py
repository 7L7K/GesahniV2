from pathlib import Path


def test_load_env_no_reload_when_unchanged(monkeypatch, tmp_path: Path):
    from app import env_utils

    env = tmp_path / ".env"
    env.write_text("FOO=1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    env_utils._ENV_PATH = Path(".env").resolve()
    env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
    env_utils._ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

    env_utils._last_mtime = None
    env_utils.load_env()
    first = env.stat().st_mtime

    env_utils._last_mtime = first
    # Should short circuit without error
    env_utils.load_env()
