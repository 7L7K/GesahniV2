#!/usr/bin/env python3

import asyncio
import os

import aiosqlite
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


def _db_path() -> str:
    return os.getenv("USERS_DB", "users.db")


async def test_password_validation():
    print("=== Password Validation Debug ===")

    # Test different users with different passwords
    test_cases = [
        ("king", "king"),
        ("king", "secret123"),
        ("admin", "admin"),
        ("admin", "secret123"),
        ("user1", "user1"),
        ("user1", "secret123"),
        ("hi", "hi"),
        ("apple", "apple"),
        ("qazwsx", "qazwsx"),
        ("qwerty", "qwerty"),
        ("test", "test"),
        ("demo", "demo"),
    ]

    for username, password in test_cases:
        print(f"\nTesting user: {username}")

        try:
            async with aiosqlite.connect(_db_path()) as db:
                async with db.execute(
                    "SELECT password_hash FROM auth_users WHERE username=?",
                    (username.lower(),),
                ) as cur:
                    row = await cur.fetchone()

            if row:
                print(f"  ✓ User found, hash length: {len(row[0])}")
                is_valid = _pwd.verify(password, row[0])
                print(f"  ✓ Password verification result: {is_valid}")
            else:
                print("  ✗ User not found in database")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_password_validation())
