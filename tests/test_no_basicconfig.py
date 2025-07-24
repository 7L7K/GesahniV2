import os

def test_no_basicConfig():
    # Only check your real app code, not tests or random scripts
    for root, dirs, files in os.walk("app"):
        for name in files:
            if name.endswith('.py'):
                with open(os.path.join(root, name), 'r', encoding='utf-8') as f:
                    code = f.read()
                    assert 'logging.basicConfig(' not in code, f"Found logging.basicConfig in {os.path.join(root, name)}"
