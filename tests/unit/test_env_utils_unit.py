from pathlib import Path


def test_load_env_prefers_real_env(monkeypatch, tmp_path: Path):
    from app import env_utils

    # create temp .env and .env.example
    real_env = tmp_path / ".env"
    real_env.write_text("FOO=real\n", encoding="utf-8")
    example = tmp_path / ".env.example"
    example.write_text("FOO=example\nBAR=example\n", encoding="utf-8")

    # point module paths to temp dir
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    # force reload bookkeeping
    env_utils._last_mtime = None
    env_utils._ENV_PATH = Path(".env").resolve()
    env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
    env_utils._ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

    env_utils.load_env()
    assert env_utils.os.getenv("FOO") == "real"


def test_load_env_uses_example_when_missing(monkeypatch, tmp_path: Path):
    from app import env_utils

    # only example exists
    example = tmp_path / ".env.example"
    example.write_text("BAZ=example\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    env_utils._last_mtime = None
    env_utils._ENV_PATH = Path(".env").resolve()
    env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
    env_utils._ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

    env_utils.load_env()
    assert env_utils.os.getenv("BAZ") == "example"


