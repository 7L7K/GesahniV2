from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import GOOGLE_OAUTH_DB_URL

ENGINE = create_engine(GOOGLE_OAUTH_DB_URL, future=True)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class GoogleToken(Base):
    __tablename__ = "google_tokens"
    # tie to your auth system; replace with your user UUID/email if needed
    user_id = Column(String, primary_key=True)
    # provider (e.g. 'google') - allow unique tokens per (user_id, provider)
    provider = Column(String, nullable=False, default="google")
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_google_tokens_user_provider"),)
    # At-rest encrypted tokens (application-level; envelope encryption recommended)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    # Optional provider identity claims useful for troubleshooting and reconciliation
    provider_iss = Column(String, nullable=True)
    provider_sub = Column(String, nullable=True)
    token_uri = Column(
        String, default="https://oauth2.googleapis.com/token", nullable=False
    )
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    scopes = Column(Text, nullable=False)  # space-separated
    expiry = Column(DateTime, nullable=False)  # UTC datetime
    rotated_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(ENGINE)
    # Lightweight migration: add rotated_at if missing (older test DBs)
    try:
        with ENGINE.begin() as conn:
            dialect = ENGINE.dialect.name
            if dialect == "sqlite":
                rows = conn.exec_driver_sql("PRAGMA table_info(google_tokens)").fetchall()
                cols = {str(r[1]) for r in rows}
                if "rotated_at" not in cols:
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN rotated_at DATETIME")
                if "provider" not in cols:
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN provider VARCHAR DEFAULT 'google'")
                if "provider_iss" not in cols:
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN provider_iss VARCHAR")
                if "provider_sub" not in cols:
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN provider_sub VARCHAR")
            else:
                # Postgres / other: try ALTER TABLE ... ADD COLUMN IF NOT EXISTS
                try:
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN IF NOT EXISTS rotated_at TIMESTAMP")
                    conn.exec_driver_sql(
                        "ALTER TABLE google_tokens ADD COLUMN IF NOT EXISTS provider VARCHAR DEFAULT 'google'"
                    )
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN IF NOT EXISTS provider_iss VARCHAR")
                    conn.exec_driver_sql("ALTER TABLE google_tokens ADD COLUMN IF NOT EXISTS provider_sub VARCHAR")
                except Exception:
                    # best-effort: ignore if individual ALTERs fail
                    pass
    except Exception:
        # best-effort; if migration fails, tests may recreate DB via env override
        pass
