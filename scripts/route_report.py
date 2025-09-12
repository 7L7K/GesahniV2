import importlib, sys, inspect
from collections import defaultdict

# Try common app import locations; adjust if needed
candidates = [
    "app.main:app",
]
app = None
errors = []
for cand in candidates:
    mod_name, _, attr = cand.partition(":")
    try:
        mod = importlib.import_module(mod_name)
        app = getattr(mod, attr)
        break
    except Exception as e:
        errors.append((cand, repr(e)))
if app is None:
    print("❌ Could not import FastAPI app. Tried:", candidates)
    for cand, err in errors:
        print(f"  - {cand}: {err}")
    sys.exit(2)

print("✅ Imported app:", app)

rows = []
dups = defaultdict(list)
for r in app.router.routes:
    path = getattr(r, "path", "")
    methods = sorted(getattr(r, "methods", set()) - {"HEAD", "OPTIONS"})
    name = getattr(r, "name", "")
    endpoint = getattr(r, "endpoint", None)
    qual = ""
    if endpoint is not None:
        qual = f"{endpoint.__module__}.{getattr(endpoint, '__qualname__', endpoint.__name__)}"
    rows.append((path, tuple(methods), name, qual))
    for m in methods:
        dups[(path, m)].append(qual)

print("\n# ROUTES")
for path, methods, name, qual in sorted(rows):
    m = ",".join(methods)
    print(f"{m:10s} {path:40s} -> {qual}")

print("\n# DUPLICATE PATH+METHOD (possible double-mounted):")
for (path, m), quals in sorted(dups.items()):
    if len(quals) > 1:
        print(f"{m:4s} {path} -> {quals}")
