Title: Make dev same-origin; delete layered CORS; canonicalize /v1/whoami; reduce envs to two knobs

Body:

Enforce Next proxy in dev; backend mounts no CORS in proxy mode.
Add strict single CORSMiddleware only when CORS_ALLOW_ORIGINS is set (prod cross-origin).
Remove custom preflight/Safari CORS layers.
Kill NEXT_PUBLIC_API_BASE; centralize on NEXT_PUBLIC_API_ORIGIN.
Canonicalize GET /v1/whoami; legacy /whoami is 308 + Deprecation.
Add Env Canary page, curl probe, ESLint + Playwright + pytest guardrails.

