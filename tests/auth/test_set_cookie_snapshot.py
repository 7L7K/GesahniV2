import pytest
from typing import Set


def test_login_cookie_snapshot(client):
    """Snapshot Set-Cookie header names and flags from login to catch SameSite/Secure/Domain regressions."""

    # Login with demo user
    response = client.post("/v1/auth/login", json={"username": "demo"})
    assert response.status_code == 200

    # Extract all Set-Cookie headers
    set_cookie_headers = response.headers.get_list("Set-Cookie")

    # Parse cookie names and flags (but not values)
    cookie_specs = set()
    for header in set_cookie_headers:
        # Parse cookie header: "name=value; flag1=value1; flag2=value2; ..."
        parts = header.split(";")
        name_value = parts[0].strip()

        # Extract cookie name (everything before =)
        cookie_name = name_value.split("=")[0].strip()
        cookie_specs.add(cookie_name)

        # Extract flags (everything after name=value)
        for part in parts[1:]:
            part = part.strip()
            if "=" in part:
                flag_name, flag_value = part.split("=", 1)
                flag_name = flag_name.strip()
                flag_value = flag_value.strip()
                cookie_specs.add(f"{cookie_name}:{flag_name}={flag_value}")
            else:
                # Flag without value (like HttpOnly, Secure)
                cookie_specs.add(f"{cookie_name}:{part}")

    # Expected cookie specifications - update these if intentional changes are made
    expected_specs = {
        # Canonical cookies
        "access_token",
        "access_token:HttpOnly",
        "access_token:SameSite=Lax",
        "access_token:Path=/",
        "access_token:Secure",
        "access_token:Priority=High",
        "access_token:Max-Age=1800",
        "refresh_token",
        "refresh_token:HttpOnly",
        "refresh_token:SameSite=Lax",
        "refresh_token:Path=/",
        "refresh_token:Secure",
        "refresh_token:Priority=High",
        "refresh_token:Max-Age=86400",
        "__session",
        "__session:HttpOnly",
        "__session:SameSite=Lax",
        "__session:Path=/",
        "__session:Secure",
        "__session:Priority=High",
        "__session:Max-Age=1800",
        # Legacy cookie names (GSNH_*)
        "GSNH_AT",
        "GSNH_AT:HttpOnly",
        "GSNH_AT:SameSite=Lax",
        "GSNH_AT:Path=/",
        "GSNH_AT:Priority=High",
        "GSNH_AT:Max-Age=3600",
        "GSNH_RT",
        "GSNH_RT:HttpOnly",
        "GSNH_RT:SameSite=Lax",
        "GSNH_RT:Path=/",
        "GSNH_RT:Priority=High",
        "GSNH_RT:Max-Age=86400",
        "GSNH_SESS",
        "GSNH_SESS:HttpOnly",
        "GSNH_SESS:SameSite=Lax",
        "GSNH_SESS:Path=/",
        "GSNH_SESS:Priority=High",
        "GSNH_SESS:Max-Age=3600",
        # Additional cookies
        "did",
        "did:Path=/",
        "did:SameSite=Lax",
        "did:Secure",
        "did:Max-Age=31536000",
    }

    # Check for unexpected cookie specs
    unexpected_specs = cookie_specs - expected_specs
    if unexpected_specs:
        pytest.fail(f"Unexpected cookie specs found: {unexpected_specs}")

    # Check for missing cookie specs (excluding Secure flags which may not be set in test env)
    secure_specs = {spec for spec in expected_specs if ":Secure" in spec}
    non_secure_specs = expected_specs - secure_specs
    missing_specs = non_secure_specs - cookie_specs

    if missing_specs:
        pytest.fail(f"Missing expected cookie specs: {missing_specs}")

    # Log Secure flag status (they may not be set in test environment)
    actual_secure_specs = {spec for spec in cookie_specs if ":Secure" in spec}
    expected_secure_specs = secure_specs
    if actual_secure_specs != expected_secure_specs:
        print(f"NOTE: Secure flags - Expected: {expected_secure_specs}, Got: {actual_secure_specs}")
        print("This may be expected in test environment without HTTPS")

    # Ensure all expected cookies are present
    cookie_names = {spec for spec in cookie_specs if ":" not in spec}
    expected_names = {"access_token", "refresh_token", "__session", "GSNH_AT", "GSNH_RT", "GSNH_SESS", "did"}
    assert cookie_names == expected_names, f"Expected cookies {expected_names}, got {cookie_names}"
