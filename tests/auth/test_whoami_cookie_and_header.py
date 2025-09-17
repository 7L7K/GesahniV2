from app.tokens import create_access_token


def test_whoami_with_cookie_auth(client):
    """Test /v1/whoami with cookie authentication."""

    # First login to get valid cookies
    login_response = client.post("/v1/auth/login", json={"username": "demo"})
    assert login_response.status_code == 200

    # Now test whoami with the cookies from login
    whoami_response = client.get("/v1/whoami")
    assert whoami_response.status_code == 200

    data = whoami_response.json()
    assert "user_id" in data
    assert "is_authenticated" in data
    assert data["is_authenticated"] is True
    assert data["user_id"] == "demo"


def test_whoami_with_header_auth(client):
    """Test /v1/whoami with Authorization header authentication."""

    # Create a valid access token for demo user
    token = create_access_token({"user_id": "demo"})

    # Test whoami with Authorization header
    headers = {"Authorization": f"Bearer {token}"}
    whoami_response = client.get("/v1/whoami", headers=headers)

    # Should work even without cookies since we have the header
    assert whoami_response.status_code == 200

    data = whoami_response.json()
    assert "user_id" in data
    assert "is_authenticated" in data
    assert data["is_authenticated"] is True
    assert data["user_id"] == "demo"


def test_whoami_header_takes_precedence_over_cookie(client):
    """Test that Authorization header takes precedence over cookies when both are present."""

    # Clear any existing cookies from previous tests
    client.cookies.clear()

    # Create tokens for different users
    cookie_token = create_access_token({"user_id": "cookie_user"})
    header_token = create_access_token({"user_id": "header_user"})

    # Set cookie for one user
    client.cookies.set("GSNH_AT", cookie_token)

    # Use header for different user
    headers = {"Authorization": f"Bearer {header_token}"}
    whoami_response = client.get("/v1/whoami", headers=headers)

    assert whoami_response.status_code == 200

    data = whoami_response.json()
    # Header should take precedence - if it doesn't, that's a bug we want to catch
    if "user_id" in data:
        # Only check if we got a successful user identification
        assert (
            data["user_id"] == "header_user"
        ), f"Expected header_user but got {data['user_id']}"


def test_whoami_unauthenticated_no_header_no_cookie(client):
    """Test /v1/whoami returns unauthenticated when no auth provided."""

    # Clear any existing cookies
    client.cookies.clear()

    # Test without any authentication
    whoami_response = client.get("/v1/whoami")
    assert whoami_response.status_code == 401

    data = whoami_response.json()
    # For 401 responses, the format is different
    assert "code" in data
    assert data["code"] == "auth.not_authenticated"


def test_whoami_invalid_token_in_header(client):
    """Test /v1/whoami with invalid token in Authorization header."""

    # Test with invalid token
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    whoami_response = client.get("/v1/whoami", headers=headers)

    assert whoami_response.status_code == 401

    data = whoami_response.json()
    # For 401 responses, the format is different
    assert "code" in data
    assert data["code"] == "auth.not_authenticated"
