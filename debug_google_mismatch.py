import asyncio
import time
import tempfile
from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken
from app.api import google_services

async def debug_mismatch():
    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    dao = TokenDAO(db_path)

    now = int(time.time())
    # Old token (account A) with calendar enabled
    a = ThirdPartyToken(
        user_id="u42",
        provider="google",
        provider_sub="sub-a",
        access_token="a_at",
        refresh_token="a_rt",
        scope="openid email profile https://www.googleapis.com/auth/calendar.readonly",
        expires_at=now + 3600,
    )
    await dao.upsert_token(a)
    print(f"Created token A: {a.id} with provider_sub: {a.provider_sub}")

    # Enable calendar on account A
    ok = await dao.update_service_status(
        user_id="u42",
        provider="google",
        service="calendar",
        status="enabled",
        provider_sub="sub-a"
    )
    print(f"Enabled calendar on token A: {ok}")

    # Ensure Token B is created after Token A by adding a small delay
    await asyncio.sleep(0.001)  # 1ms delay to ensure different timestamps

    # New token (account B) more recent - explicitly set created_at to be newer
    b = ThirdPartyToken(
        user_id="u42",
        provider="google",
        provider_sub="sub-b",
        access_token="b_at",
        refresh_token="b_rt",
        scope="openid email profile https://www.googleapis.com/auth/gmail.readonly",
        expires_at=now + 7200,
        created_at=now + 10,  # Make it 10 seconds newer
    )
    await dao.upsert_token(b)
    print(f"Created token B: {b.id} with provider_sub: {b.provider_sub}")

    # Check what get_token returns
    current_token = await dao.get_token("u42", "google")
    print(f"get_token returned: {current_token.id if current_token else None} with provider_sub: {current_token.provider_sub if current_token else None}")

    # Check what get_all_user_tokens returns
    all_tokens = await dao.get_all_user_tokens("u42")
    print(f"All tokens count: {len(all_tokens)}")
    for i, token in enumerate(all_tokens):
        print(f"  Token {i}: {token.id} provider_sub: {token.provider_sub} service_state: {token.service_state} created_at: {token.created_at}")

    # Check token creation times
    print(f"Token A created_at: {a.created_at}")
    print(f"Token B created_at: {b.created_at}")
    print(f"Time difference: {b.created_at - a.created_at} seconds")

    # Monkeypatch for testing - patch the module-level functions
    import app.auth_store_tokens as auth_mod

    # Store original functions
    original_get_token = auth_mod.get_token
    original_get_all_user_tokens = auth_mod.get_all_user_tokens

    async def mock_get_token(user_id: str, provider: str, provider_sub=None):
        print(f"Mock get_token called: {user_id}, {provider}, {provider_sub}")
        result = await dao.get_token(user_id, provider, provider_sub)
        print(f"Mock get_token returning: {result.id if result else None}")
        return result

    async def mock_get_all_user_tokens(user_id: str):
        print(f"Mock get_all_user_tokens called: {user_id}")
        result = await dao.get_all_user_tokens(user_id)
        print(f"Mock get_all_user_tokens returning: {len(result)} tokens")
        return result

    # Monkeypatch
    auth_mod.get_token = mock_get_token
    auth_mod.get_all_user_tokens = mock_get_all_user_tokens
    google_services.get_current_user_id = lambda request=None: "u42"

    # Let's manually check the account mismatch logic
    current_token = await dao.get_token("u42", "google")
    all_tokens = await dao.get_all_user_tokens("u42")

    print(f"\n=== Account Mismatch Debug ===")
    print(f"Current token: {current_token.id} provider_sub: {current_token.provider_sub}")
    print(f"All tokens: {len(all_tokens)}")

    for i, oth in enumerate(all_tokens):
        print(f"  Checking token {i}: {oth.id} provider_sub: {oth.provider_sub}")
        if getattr(oth, "provider_sub", None) and getattr(oth, "provider_sub", None) != getattr(current_token, "provider_sub", None):
            print(f"    Different provider_sub detected: {oth.provider_sub} != {current_token.provider_sub}")
            from app.service_state import parse as parse_state_func
            st = parse_state_func(getattr(oth, "service_state", None))
            print(f"    Parsed service_state: {st}")
            for svc_name, entry in st.items():
                print(f"      Service {svc_name}: {entry}")
                if entry.get("status") == "enabled":
                    print(f"        Found enabled service: {svc_name} - should raise account_mismatch!")
                    break

    try:
        await google_services.enable_service("gmail", request=None)
        print("enable_service succeeded (unexpected)")
    except Exception as e:
        print(f"enable_service failed with: {type(e).__name__}")
        if hasattr(e, 'detail') and isinstance(e.detail, dict):
            print(f"Error code: {e.detail.get('code')}")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_mismatch())
