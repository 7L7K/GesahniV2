import os


def test_no_basicConfig():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    for root, _, files in os.walk(repo_root):
        for name in files:
            if name.endswith('.py') and name != 'test_no_basicconfig.py':
                with open(os.path.join(root, name), 'r', encoding='utf-8') as f:
                    assert 'logging.basicConfig(' not in f.read()
