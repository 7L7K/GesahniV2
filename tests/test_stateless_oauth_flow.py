#!/usr/bin/env python3
"""
Comprehensive test script to demonstrate the stateless OAuth flow with detailed logging.

This script shows the complete flow from connect to callback, demonstrating
how the stateless implementation works even without cookies.
"""

import asyncio
import time
import uuid

import jwt

from app.api.auth import _jwt_secret
from app.api.oauth_store import dump_store, pop_tx, put_tx


async def test_stateless_oauth_flow():
    """Test the complete stateless OAuth flow with comprehensive logging."""
    print("🎯 Testing Stateless OAuth Flow with Comprehensive Logging")
    print("=" * 70)
    print()

    # Step 1: Simulate Spotify Connect
    print("📍 STEP 1: Spotify Connect (Stateless)")
    print("-" * 40)

    # Generate a transaction ID and PKCE data
    tx_id = str(uuid.uuid4())
    user_id = "test_user_123"
    code_verifier = "test_code_verifier_" + str(uuid.uuid4())[:20]

    print(f"Transaction ID: {tx_id}")
    print(f"User ID: {user_id}")
    print(f"Code Verifier: {code_verifier[:30]}...")
    print()

    # Store transaction data
    print("Storing transaction data in oauth_store...")
    tx_data = {
        "user_id": user_id,
        "code_verifier": code_verifier,
        "ts": int(time.time()),
    }
    put_tx(tx_id, tx_data, ttl_seconds=600)
    print()

    # Create JWT state
    print("Creating JWT state...")
    state_payload = {"tx": tx_id, "uid": user_id, "exp": int(time.time()) + 600}

    secret = _jwt_secret()
    state = jwt.encode(state_payload, secret, algorithm="HS256")
    print(f"JWT State: {state[:60]}...")
    print()

    # Step 2: Simulate user authorization redirect
    print("📍 STEP 2: User Authorization Redirect")
    print("-" * 40)
    print("User would be redirected to Spotify with the JWT state...")
    print(f"Authorization URL would contain: state={state[:50]}...")
    print()

    # Step 3: Simulate Spotify callback
    print("📍 STEP 3: Spotify Callback (Stateless)")
    print("-" * 40)

    # Decode the JWT state (as the callback would do)
    print("Decoding JWT state...")
    decoded = jwt.decode(state, secret, algorithms=["HS256"])
    callback_tx_id = decoded["tx"]
    callback_user_id = decoded["uid"]

    print(f"Decoded Transaction ID: {callback_tx_id}")
    print(f"Decoded User ID: {callback_user_id}")
    print()

    # Recover transaction from store
    print("Recovering transaction from oauth_store...")
    recovered_tx = pop_tx(callback_tx_id)

    if recovered_tx:
        print("✅ Transaction recovered successfully!")
        print(f"Stored User ID: {recovered_tx['user_id']}")
        print(f"Code Verifier: {recovered_tx['code_verifier'][:30]}...")
        print(f"Transaction Age: {int(time.time() - recovered_tx['ts'])} seconds")
    else:
        print("❌ Transaction not found!")
    print()

    # Step 4: Simulate token exchange
    print("📍 STEP 4: Token Exchange")
    print("-" * 40)
    print("Would exchange authorization code for access tokens...")
    print(f"Using Code Verifier: {recovered_tx['code_verifier'][:30]}...")
    print()

    # Step 5: Simulate token persistence
    print("📍 STEP 5: Token Persistence")
    print("-" * 40)
    print("Would persist tokens to database...")
    print(f"User ID: {callback_user_id}")
    print("Provider: spotify")
    print()

    # Step 6: Show final state
    print("📍 STEP 6: Final State")
    print("-" * 40)
    print("Dumping oauth_store state...")
    store_dump = dump_store()

    print(f"Store size: {store_dump['store_size']}")
    print(f"Active transactions: {len(store_dump['transactions'])}")
    print()

    print("🎉 Stateless OAuth Flow Test Complete!")
    print()
    print("Key Benefits Demonstrated:")
    print("✅ No cookies required for the OAuth flow")
    print("✅ JWT state contains all necessary information")
    print("✅ PKCE code_verifier stored server-side securely")
    print("✅ Atomic transaction handling with automatic cleanup")
    print("✅ Comprehensive logging throughout the entire process")


if __name__ == "__main__":
    asyncio.run(test_stateless_oauth_flow())
