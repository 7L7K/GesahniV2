import psycopg2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get connection to test PostgreSQL database."""
    return psycopg2.connect(
        "postgresql://app:app_pw@localhost:5432/gesahni_test",
        cursor_factory=RealDictCursor,
    )


def test_register_and_duplicate():
    """Test user registration and duplicate prevention using PostgreSQL."""
    from app.api.auth import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Clean up any existing test users
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM auth.users WHERE email LIKE 'alice%' OR email LIKE 'test_%'"
        )
        conn.commit()
    conn.close()

    resp = client.post(
        "/v1/auth/register", json={"username": "alice", "password": "secret"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Verify user was created in PostgreSQL
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM auth.users WHERE email = %s", ("alice",))
        row = cur.fetchone()
        assert row is not None
        stored = row["password_hash"]
    conn.close()

    assert stored != "secret"
    assert auth.pwd_context.verify("secret", stored)

    resp2 = client.post(
        "/v1/auth/register", json={"username": "alice", "password": "x"}
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "username_taken"


def test_register_is_public_endpoint():
    """Test that register endpoint is public and doesn't require authentication."""
    from app.api.auth import router

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    # Clean up any existing test users
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM auth.users WHERE email LIKE 'bob%' OR email LIKE 'test_%'"
        )
        conn.commit()
    conn.close()

    # Register should work without any authentication
    resp = client.post(
        "/v1/auth/register", json={"username": "bob", "password": "secret"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Verify the user was actually created in PostgreSQL
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM auth.users WHERE email = %s", ("bob",))
        row = cur.fetchone()
        assert row is not None
        stored = row["password_hash"]
    conn.close()

    assert stored != "secret"
    assert auth.pwd_context.verify("secret", stored)
