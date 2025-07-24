import os
import sys
import subprocess
from pathlib import Path


def test_record_session_cli(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    capture_file = repo_root / "app" / "capture.py"

    stub = (
        "def record(duration, output_dir):\n"
        "    from pathlib import Path\n"
        "    p = Path(output_dir) / 'saved.txt'\n"
        "    p.write_text('data')\n"
        "    return str(p)\n"
    )

    original = capture_file.read_text() if capture_file.exists() else None
    capture_file.write_text(stub)

    script = repo_root / "record_session.py"
    out_dir = tmp_path / "sessions"
    result = subprocess.run(
        [sys.executable, str(script), "--duration", "5", "--output", str(out_dir)],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    if original is None:
        capture_file.unlink()
    else:
        capture_file.write_text(original)

    assert result.returncode == 0
    saved_path = out_dir / "saved.txt"
    assert saved_path.exists()
    assert str(saved_path) in result.stdout
