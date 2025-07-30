import os, sys, asyncio, inspect, importlib, pkgutil, pathlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

from app.skills import base


def test_all_skill_modules_have_handle():
    skills_path = pathlib.Path(__file__).resolve().parents[1] / "app" / "skills"
    for info in pkgutil.iter_modules([str(skills_path)]):
        if info.name.startswith("_") or info.name == "base":
            continue
        mod = importlib.import_module(f"app.skills.{info.name}")
        found = False
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, base.Skill) and obj is not base.Skill:
                inst = obj()
                assert inspect.iscoroutinefunction(inst.handle)
                found = True
        assert found, f"{info.name} has no Skill subclass"
