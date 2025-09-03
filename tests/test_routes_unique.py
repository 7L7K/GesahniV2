from collections import Counter

from app.main import app


def test_no_duplicate_google_oauth_login_route():
    pairs = [(m, r.path) for r in app.routes for m in getattr(r, "methods", set())]
    c = Counter(pairs)
    # Canonical Google OAuth login URL should be unique
    assert c[("GET", "/v1/google/auth/login_url")] == 1


def test_no_duplicate_auth_routes_prefix():
    pairs = [(m, r.path) for r in app.routes for m in getattr(r, "methods", set())]
    # At most one provider should own /v1/auth/* routes
    auth_routes = [p for p in pairs if p[1].startswith("/v1/auth/")]
    # Ensure uniqueness across method+path
    from collections import Counter as C

    counts = C(auth_routes)
    assert all(v == 1 for v in counts.values())
