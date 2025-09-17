"""
Database test configuration - overrides main conftest.py fixtures
"""

import os

import pytest
from sqlalchemy import create_engine


@pytest.fixture(scope="session")
def sync_engine():
    """Use the existing database for testing instead of creating a new one."""
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni"
    )
    return create_engine(database_url)


# Override the per_worker_database fixture from main conftest.py
@pytest.fixture(scope="session")
def per_worker_database():
    """Skip database creation - use existing database."""
    # Don't create a test database, just use the existing one
    yield os.getenv("DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni")
