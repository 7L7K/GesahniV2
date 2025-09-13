import inspect
from app.main import app

paths = {}
for r in app.routes:
    try:
        path = r.path
        if not path.startswith("/v1/auth") and path not in ("/v1/whoami", "/v1/csrf"):
            continue
        endpoint = getattr(r, "endpoint", None)
        src = "unknown"
        if endpoint:
            src = inspect.getsourcefile(endpoint) or "unknown"
        paths.setdefault(path, []).append(src)
    except Exception:
        pass

for p, srcs in sorted(paths.items()):
    print(p, "->")
    for s in sorted(set(srcs)):
        print("   ", s)
