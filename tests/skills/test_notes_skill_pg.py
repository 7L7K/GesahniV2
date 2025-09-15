import asyncio
import os

import psycopg2
from psycopg2.extras import RealDictCursor


def _conn():
    url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni_test"
    )
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def test_notes_skill_persists_in_user_data_schema():
    # Ensure user exists for system user id used by skill
    system_user_id = "00000000-0000-0000-0000-000000000001"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.users (id, email, name, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                (system_user_id, f"{system_user_id}@test.local", "System User"),
            )
            conn.commit()

    async def run_skill():
        from app.skills.notes_skill import NotesSkill

        s = NotesSkill()
        # Add a note
        resp = await s.run(
            "note buy milk",
            type(
                "M",
                (),
                {
                    "re": type("R", (), {"pattern": "note"}),
                    "group": lambda self, i: "buy milk",
                },
            )(),
        )
        assert resp == "Noted."
        # List notes
        resp2 = await s.run(
            "list notes",
            type("M", (), {"re": type("R", (), {"pattern": "list notes"})})(),
        )
        assert "buy milk" in resp2

    asyncio.get_event_loop().run_until_complete(run_skill())

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT text FROM user_data.notes WHERE user_id=%s ORDER BY created_at DESC LIMIT 1",
                (system_user_id,),
            )
            row = cur.fetchone()
            assert row and row["text"]
