#!/usr/bin/env python3
"""
Token Management Script for GesahniV2

This script helps manage JWT tokens and provides utilities for:
1. Checking token expiration
2. Generating fresh tokens
3. Updating cookies with new tokens
4. Monitoring token status

Usage:
    python scripts/manage_tokens.py check
    python scripts/manage_tokens.py refresh
    python scripts/manage_tokens.py generate
"""

import os
import sys
import jwt
import time
import json
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tokens import make_access, make_refresh


def check_token_expiration():
    """Check expiration status of tokens in cookies.txt"""
    # Use absolute path to avoid working directory issues
    cookie_file = Path("/Users/kingal/2025/GesahniV2/cookies.txt")

    if not cookie_file.exists():
        print("❌ No cookies.txt file found")
        print(f"   Expected location: {cookie_file.absolute()}")
        return

    print("🔍 Checking token expiration in cookies.txt...")

    with open(cookie_file, "r") as f:
        for line in f:
            if "GSNH_AT" in line:  # Access token
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    token = parts[6]
                    try:
                        payload = jwt.decode(token, options={"verify_signature": False})
                        exp_time = payload.get("exp", 0)
                        current_time = time.time()
                        remaining = exp_time - current_time

                        if remaining > 0:
                            minutes = int(remaining / 60)
                            hours = int(minutes / 60)
                            print(f"✅ Access token: Valid for {hours}h {minutes%60}m")
                            print(
                                f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp_time))}"
                            )
                        else:
                            expired_minutes = int(abs(remaining) / 60)
                            print(
                                f"❌ Access token: EXPIRED {expired_minutes} minutes ago"
                            )
                    except Exception as e:
                        print(f"❌ Access token: Invalid format - {e}")

            elif "GSNH_RT" in line:  # Refresh token
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    token = parts[6]
                    try:
                        payload = jwt.decode(token, options={"verify_signature": False})
                        exp_time = payload.get("exp", 0)
                        current_time = time.time()
                        remaining = exp_time - current_time

                        if remaining > 0:
                            hours = int(remaining / 3600)
                            days = int(hours / 24)
                            print(f"✅ Refresh token: Valid for {days}d {hours%24}h")
                            print(
                                f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp_time))}"
                            )
                        else:
                            expired_hours = int(abs(remaining) / 3600)
                            print(
                                f"❌ Refresh token: EXPIRED {expired_hours} hours ago"
                            )
                    except Exception as e:
                        print(f"❌ Refresh token: Invalid format - {e}")


def generate_fresh_tokens():
    """Generate fresh JWT tokens"""
    print("🔄 Generating fresh JWT tokens...")

    # Create access token
    access_data = {
        "user_id": "testuser",
        "sub": "testuser",
        "type": "access",
        "scopes": ["care:resident", "music:control", "chat:write"],
    }
    access_token = make_access(access_data)

    # Create refresh token
    refresh_data = {"user_id": "testuser", "sub": "testuser", "type": "refresh"}
    refresh_token = make_refresh(refresh_data)

    print("✅ Fresh tokens generated!")
    print(f"Access Token: {access_token[:50]}...")
    print(f"Refresh Token: {refresh_token[:50]}...")

    return access_token, refresh_token


def update_cookies_file(access_token, refresh_token):
    """Update cookies.txt with fresh tokens"""
    cookie_file = Path("/Users/kingal/2025/GesahniV2/cookies.txt")

    # Read existing cookies
    cookies = []
    if cookie_file.exists():
        with open(cookie_file, "r") as f:
            cookies = f.readlines()

    # Update or add tokens
    updated_cookies = []
    access_updated = False
    refresh_updated = False

    for line in cookies:
        if line.startswith("#HttpOnly_localhost") and "GSNH_AT" in line:
            # Update access token cookie
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                parts[6] = access_token
                updated_cookies.append("\t".join(parts) + "\n")
                access_updated = True
            else:
                updated_cookies.append(line)
        elif line.startswith("#HttpOnly_localhost") and "GSNH_RT" in line:
            # Update refresh token cookie
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                parts[6] = refresh_token
                updated_cookies.append("\t".join(parts) + "\n")
                refresh_updated = True
            else:
                updated_cookies.append(line)
        else:
            updated_cookies.append(line)

    # Write back to file
    with open(cookie_file, "w") as f:
        f.writelines(updated_cookies)

    print(f"✅ Cookies updated: Access={access_updated}, Refresh={refresh_updated}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/manage_tokens.py <command>")
        print("Commands:")
        print("  check    - Check token expiration status")
        print("  refresh  - Generate and update fresh tokens")
        print("  generate - Generate fresh tokens (don't update cookies)")
        return

    command = sys.argv[1]

    if command == "check":
        check_token_expiration()
    elif command == "refresh":
        access_token, refresh_token = generate_fresh_tokens()
        update_cookies_file(access_token, refresh_token)
        print("🎉 Token refresh complete!")
    elif command == "generate":
        access_token, refresh_token = generate_fresh_tokens()
        print("\n📋 Copy these tokens to update your cookies:")
        print(f"Access: {access_token}")
        print(f"Refresh: {refresh_token}")
    else:
        print(f"❌ Unknown command: {command}")


if __name__ == "__main__":
    main()
