import importlib
import pkgutil


def test_all_modules_importable():
    for mod in pkgutil.iter_modules(['app']):
        importlib.import_module(f'app.{mod.name}')


def test_no_logging_basic_config():
    import pathlib

    for path in pathlib.Path('.').rglob('*.py'):
        if path.name == 'test_imports.py':
            continue
        text = path.read_text()
        assert 'logging.basicConfig(' not in text, f'basicConfig found in {path}'

