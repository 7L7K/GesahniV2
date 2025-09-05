import secrets, json, sys

def hs256():
    print(secrets.token_urlsafe(64))

def rs256():
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
    except Exception:
        print("Install 'cryptography' to generate RS keys.", file=sys.stderr); sys.exit(1)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    print(json.dumps({"kid1": priv_pem}))
    print(json.dumps({"kid1": pub_pem}))

if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if cmd == "hs256": hs256()
    elif cmd == "rs256": rs256()
    else: print("Usage: python scripts/jwt_tools.py [hs256|rs256]")
