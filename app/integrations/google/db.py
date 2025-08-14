from __future__ import annotations
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import GOOGLE_OAUTH_DB_URL

ENGINE = create_engine(GOOGLE_OAUTH_DB_URL, future=True)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

class GoogleToken(Base):
    __tablename__ = "google_tokens"
    # tie to your auth system; replace with your user UUID/email if needed
    user_id = Column(String, primary_key=True)
    # At-rest encrypted tokens (application-level; envelope encryption recommended)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_uri = Column(String, default="https://oauth2.googleapis.com/token", nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    scopes = Column(Text, nullable=False)  # space-separated
    expiry = Column(DateTime, nullable=False)  # UTC datetime
    rotated_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(ENGINE)
