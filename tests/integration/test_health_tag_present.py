"""Health tag presence test - ensures Health routes have correct tags."""

import importlib


def test_health_routes_have_health_tag():
    """Ensure health routes have the Health tag in their OpenAPI operations.

    This prevents accidental removal of the health router's tags=["Health"]
    which would break API documentation and client expectations.
    """
    app = importlib.import_module("app.main").create_app()

    # Get OpenAPI schema
    openapi_schema = app.openapi()
    paths = openapi_schema.get("paths", {})

    # Find health routes and check they have Health tag
    health_routes_found = 0
    for path, methods in paths.items():
        if "health" in path.lower():
            for method, details in methods.items():
                if method.upper() in ["GET", "POST", "PUT", "DELETE"]:
                    tags = details.get("tags", [])
                    assert (
                        "Health" in tags
                    ), f"Health route {path} missing Health tag: {tags}"
                    health_routes_found += 1

    # Ensure we found some health routes
    assert health_routes_found > 0, "No health routes found in OpenAPI schema"

    # Sanity check that we have some paths
    assert len(paths) > 0, "No paths found in OpenAPI schema"
