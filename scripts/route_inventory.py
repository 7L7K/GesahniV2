from collections import defaultdict
import importlib
from pprint import pprint

# Change this import to your FastAPI app module
app = importlib.import_module("app.main").app

rows = []
seen = defaultdict(list)

for r in app.routes:
    methods = sorted(getattr(r, "methods", []) or [])
    path = getattr(r, "path", None)
    name = getattr(r, "name", None)
    if not path or not methods:
        continue
    for m in methods:
        key = (m, path)
        seen[key].append(name)
        rows.append({"method": m, "path": path, "name": name})

dupes = {k:v for k,v in seen.items() if len(v) > 1}
print("\n== ROUTES ==")
pprint(sorted(rows, key=lambda x:(x["path"], x["method"], x["name"])))
print("\n== DUPLICATES ==")
pprint(dupes)
# exit nonzero on dupes
import sys; sys.exit(1 if dupes else 0)
