import importlib
import pkgutil
import pathlib


def test_import_all_modules():
    pkg_path = pathlib.Path(__file__).resolve().parents[1] / "app"
    for module in pkgutil.iter_modules([str(pkg_path)]):
        importlib.import_module(f"app.{module.name}")
