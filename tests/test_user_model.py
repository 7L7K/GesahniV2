import os

# Use an in-memory SQLite database for tests
os.environ["USERS_DB"] = "sqlite:///:memory:"

from app.models import user as user_model


def test_user_crud_cycle():
    user_model.init_db()
    with user_model.get_session() as db:
        created = user_model.create_user(db, "alice", "hashed")
        assert created.id is not None

        fetched = user_model.get_user(db, "alice")
        assert fetched.username == "alice"

        user_model.update_login(db, fetched)
        assert fetched.login_count == 1
        assert fetched.last_login is not None

        users = user_model.list_users(db)
        assert len(users) == 1

        user_model.delete_user(db, fetched)
        assert user_model.get_user(db, "alice") is None
