import os


def test_no_basicConfig():
    # Only check your real app code, not tests or random scripts
    # Allow basicConfig in entrypoints (main.py, CLI scripts) but not in library modules
    for root, _dirs, files in os.walk("app"):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    code = f.read()

                # Skip entrypoints that are allowed to use basicConfig
                if name == "main.py":  # Main app entrypoint
                    continue
                if 'if __name__ == "__main__":' in code:  # CLI entrypoints
                    continue

                assert (
                    "logging.basicConfig(" not in code
                ), f"Found logging.basicConfig in {os.path.join(root, name)}"
