"""User model and CRUD helpers using SQLAlchemy."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Database configuration
DATABASE_URL = os.getenv("USERS_DB", "sqlite:///./users.db")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    """Simple user representation."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    login_count = Column(Integer, default=0)
    last_login = Column(DateTime)


def init_db() -> None:
    """Create database tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)


# CRUD helper functions


def get_session() -> Session:
    """Return a new session bound to the engine."""
    return SessionLocal()


def create_user(db: Session, username: str, hashed_password: str) -> User:
    user = User(username=username, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session) -> Iterable[User]:
    return db.query(User).all()


def update_login(db: Session, user: User) -> User:
    user.login_count += 1
    user.last_login = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()
