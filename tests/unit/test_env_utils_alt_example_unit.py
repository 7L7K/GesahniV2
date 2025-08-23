from pathlib import Path


def test_load_env_alt_example(monkeypatch, tmp_path: Path):
    from app import env_utils

    alt = tmp_path / "env.example"
    alt.write_text("ALT=1\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    env_utils._last_mtime = None
    env_utils._ENV_PATH = Path(".env").resolve()
    env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
    env_utils._ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

    env_utils.load_env()
    assert env_utils.os.getenv("ALT") == "1"
