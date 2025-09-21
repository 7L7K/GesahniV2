#!/usr/bin/env python3
"""
JWT decoder - safely decode JWT tokens for analysis (dev only)
"""
import os
import sys
import json
import jwt

def decode_jwt_tokens():
    secret = os.getenv('JWT_SECRET', 'dev-secret')
    
    # Read tokens from stdin or cookies file
    if len(sys.argv) > 1:
        # Read from cookies file
        cookie_file = sys.argv[1]
        try:
            with open(cookie_file, 'r') as f:
                content = f.read()
            # Extract GSNH_ tokens
            tokens = []
            for line in content.split('\n'):
                if 'GSNH_' in line and '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        tokens.append(parts[6])
        except Exception as e:
            print(f"Error reading cookie file: {e}")
            return
    else:
        # Read from stdin
        tokens = sys.stdin.read().split()
    
    print("=== JWT Token Analysis ===")
    for i, token in enumerate(tokens, 1):
        if not token or token == '""':
            continue
            
        print(f"\nToken {i}: {token[:50]}...")
        try:
            decoded = jwt.decode(token, secret, algorithms=["HS256"])
            print(f"  ✅ Valid JWT")
            print(f"  Payload: {json.dumps(decoded, indent=2)}")
        except jwt.ExpiredSignatureError:
            print(f"  ❌ Expired token")
        except jwt.InvalidTokenError as e:
            print(f"  ❌ Invalid token: {e}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    decode_jwt_tokens()
