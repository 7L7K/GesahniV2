import os, json

KEEP = [
    "ENV","HOST","APP_URL",
    "COOKIE_SAMESITE","COOKIE_SECURE","GSN_ENABLE_AUTH_COOKIES","CSRF_ENABLED",
    "JWT_ALGS","JWT_EXPIRE_MINUTES","JWT_REFRESH_EXPIRE_MINUTES","JWT_SECRET",
    "CORS_ALLOW_ORIGINS","CORS_ALLOW_CREDENTIALS",
    "OPENAI_API_KEY","SPOTIFY_CLIENT_ID","SPOTIFY_CLIENT_SECRET","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET",
    "LLAMA_ENABLED","OLLAMA_URL","EMBEDDING_BACKEND","EMBED_MODEL",
]

env_values = {}
for k in KEEP:
    if "KEY" in k or "SECRET" in k:
        env_values[k] = "<set>" if os.getenv(k) else None
    else:
        env_values[k] = os.getenv(k)

print(json.dumps(env_values, indent=2))
