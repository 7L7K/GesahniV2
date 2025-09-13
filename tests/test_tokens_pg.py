import os
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor


def _conn():
    url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni_test"
    )
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def test_tokens_unique_triplet_and_allows_diff_sub():
    user_id = str(uuid.uuid4())
    provider = "spotify"
    sub1 = f"sub_{uuid.uuid4().hex[:8]}"
    sub2 = f"sub_{uuid.uuid4().hex[:8]}"

    with _conn() as conn:
        with conn.cursor() as cur:
            # ensure user exists
            cur.execute(
                """
                INSERT INTO auth.users (id, email, name, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, f"{user_id}@test.local", "Test User"),
            )
            # insert first token
            cur.execute(
                """
                INSERT INTO tokens.third_party_tokens (user_id, provider, provider_sub, access_token, expires_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW() + INTERVAL '1 hour', NOW())
                """,
                (user_id, provider, sub1, "Btok_1"),
            )
            conn.commit()

            # duplicate triplet must fail
            raised = False
            try:
                cur.execute(
                    """
                    INSERT INTO tokens.third_party_tokens (user_id, provider, provider_sub, access_token, expires_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW() + INTERVAL '1 hour', NOW())
                    """,
                    (user_id, provider, sub1, "Btok_dup"),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raised = True

            assert (
                raised
            ), "Expected unique violation for duplicate (user_id, provider, provider_sub)"

            # different provider_sub is allowed
            cur.execute(
                """
                INSERT INTO tokens.third_party_tokens (user_id, provider, provider_sub, access_token, expires_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW() + INTERVAL '1 hour', NOW())
                """,
                (user_id, provider, sub2, "Btok_2"),
            )
            conn.commit()

            cur.execute(
                "SELECT COUNT(*) AS c FROM tokens.third_party_tokens WHERE user_id=%s AND provider=%s",
                (user_id, provider),
            )
            c = cur.fetchone()["c"]
            assert c == 2
