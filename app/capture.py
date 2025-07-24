import subprocess

def capture_audio(path: str, duration: int = 3) -> None:
    """Record audio using the system 'arecord' command."""
    cmd = ["arecord", "-d", str(duration), "-f", "cd", "-t", "wav", path]
    subprocess.run(cmd, check=True)
