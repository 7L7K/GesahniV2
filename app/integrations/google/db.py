from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint, text
from sqlalchemy.orm import declarative_base

from app.db.core import sync_engine

# Use PostgreSQL through app.db.core instead of direct SQLite engine
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
    """Initialize PostgreSQL tables for Google OAuth tokens."""
    # Create tables using PostgreSQL through app.db.core
    Base.metadata.create_all(sync_engine)

    # Lightweight migration: add columns if missing (PostgreSQL compatible)
    try:
        with sync_engine.begin() as conn:
            # Use PostgreSQL-specific ALTER TABLE syntax
            try:
                # Add rotated_at column if missing
                conn.execute(text("""
                    ALTER TABLE google_tokens
                    ADD COLUMN IF NOT EXISTS rotated_at TIMESTAMP
                """))
                # Add provider column if missing
                conn.execute(text("""
                    ALTER TABLE google_tokens
                    ADD COLUMN IF NOT EXISTS provider VARCHAR DEFAULT 'google'
                """))
                # Add provider_iss column if missing
                conn.execute(text("""
                    ALTER TABLE google_tokens
                    ADD COLUMN IF NOT EXISTS provider_iss VARCHAR
                """))
                # Add provider_sub column if missing
                conn.execute(text("""
                    ALTER TABLE google_tokens
                    ADD COLUMN IF NOT EXISTS provider_sub VARCHAR
                """))
            except Exception:
                # best-effort: ignore if individual ALTERs fail (columns may already exist)
                pass
    except Exception:
        # best-effort; if migration fails, tests may recreate DB via env override
        pass
