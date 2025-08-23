import ast
from pathlib import Path


def _find_whoami_defs(root: Path) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for p in root.rglob("*.py"):
        if any(part.startswith(".") for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            # Look for decorator @router.get("/whoami") or variations
            decos = getattr(node, "decorator_list", [])
            for d in decos:
                try:
                    if (
                        isinstance(d, ast.Call)
                        and hasattr(d.func, "attr")
                        and d.func.attr in {"get", "post"}
                    ):
                        if (
                            len(d.args) >= 1
                            and isinstance(d.args[0], ast.Constant)
                            and str(d.args[0].value).endswith("/whoami")
                        ):
                            results.append((str(p), getattr(d, "lineno", 0)))
                except Exception:
                    pass
    return results


def test_single_whoami_definition():
    # Restrict scan to app/api to avoid counting helper/demo routes elsewhere
    root = Path(__file__).resolve().parents[2] / "app" / "api"
    defs = _find_whoami_defs(root)
    # Allow exactly one definition under app/
    assert len(defs) == 1, f"Expected 1 /whoami route, found {len(defs)}: {defs}"
