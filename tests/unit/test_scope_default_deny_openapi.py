from app.main import app

PRIVILEGED_TAGS = {"Admin", "Care", "HomeAssistant", "Ops"}


def test_privileged_routes_require_scopes_in_openapi():
    schema = app.openapi()
    offenders = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            tags = set(op.get("tags", []))
            if not (tags & PRIVILEGED_TAGS):
                continue
            sec = op.get("security", [])
            has_scopes = False
            for entry in sec:
                for _, scopes in entry.items():
                    if scopes:
                        has_scopes = True
            if not has_scopes:
                offenders.append((method.upper(), path, tuple(sorted(tags))))
    assert not offenders, f"Privileged routes missing scopes: {offenders}"


