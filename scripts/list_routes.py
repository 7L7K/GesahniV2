from app.main import app

rows = []
for r in app.routes:
    methods = getattr(r, "methods", None)
    path = getattr(r, "path", "")
    name = getattr(r, "name", "")
    kind = r.__class__.__name__
    if methods:
        rows.append((sorted(methods), path, name, kind))
    else:
        # Treat as WS for display purposes
        rows.append((["WS"], path, name, kind))

for methods, path, name, kind in sorted(rows, key=lambda x: ("/".join(x[0]), x[1])):
    print(f"{'/'.join(methods):8}  {path:40}  {name}  [{kind}]")

