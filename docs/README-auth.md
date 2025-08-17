# Auth Setup Guide (Local & Prod)

This guide covers Clerk setup, environment variables, roles configuration, redirect URIs, optional passkeys/magic links, and rollback switches for GesahniV2.

## Overview
- Frontend: Next.js app with Clerk UI components (`ClerkProvider`, `SignInButton`, etc.).
- Backend: FastAPI validates JWTs via HS256 (local) and/or Clerk JWKS (RS256). Role gates enforce `admin`, `caregiver`, `resident`.
- Device pairing: generates resident-scoped device tokens for TVs.

## Clerk Dashboard Steps (Dev instance)
1) Create an application in Clerk.
2) Retrieve keys:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - `CLERK_SECRET_KEY` (frontend not used directly but kept for completeness)
3) Allowed redirect URLs:
   - `http://localhost:3000/sign-in` and `http://localhost:3000/sign-up`
   - Add prod URLs when deploying (e.g., `https://app.example.com/sign-in`).
4) Optional: Enable Magic Links or Passkeys in Clerk → affects sign-in experience only.
5) Roles:
   - Use Clerk user metadata or organization roles to set a `roles` claim (array or string). Common values: `admin`, `caregiver`, `resident`.
   - Alternatively mirror from scopes if using a custom JWT template: `admin` from `admin:write`, `caregiver` from `care:caregiver`, `resident` from `care:resident`.

## Frontend `.env.local`
```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
```

## Backend env (.env or process env)
```
# Local HS256 JWT
JWT_SECRET=change-me

# Clerk JWT (RS256) verification (any of the following)
CLERK_JWKS_URL=https://<tenant>.clerk.accounts.dev/.well-known/jwks.json
# or
CLERK_ISSUER=https://<tenant>.clerk.accounts.dev
# Optional audience enforcement
CLERK_AUDIENCE=<your-publishable-key-or-aud>

# Optional Redis for device tokens, pairing codes, rate-limit distribution
REDIS_URL=redis://localhost:6379/0

# Device/TV pairing TTLs
DEVICE_PAIR_CODE_TTL_S=300
DEVICE_TOKEN_TTL_S=2592000
```

## Running locally
- Backend:
```
uvicorn app.main:app --reload
```
- Frontend:
```
cd frontend
npm install
npm run dev
```
Visit `http://localhost:3000`.

## Production notes
- Ensure HTTPS and proper `NEXT_PUBLIC_SITE_URL` (if used) for social/OG tags.
- Configure Clerk production instance with domain and redirect URLs.
- Set `JWT_SECRET` for legacy/dev HS256 tokens if needed; RS256 via Clerk JWKS preferred.
- Redis strongly recommended for device tokens and pairing codes.

## Roles & gates
- Admin routes: `require_roles(["admin"])` → 403 for non-admin.
- Care routes: caregiver/resident as appropriate (WS and HTTP).
- Device tokens: resident scope only; cannot access admin endpoints.

## Rollback switches
- Disable Clerk temporarily by unsetting `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (frontend) and `CLERK_*` envs (backend). Frontend will fall back to legacy cookie/JWT flow; backend will continue to accept HS256 tokens under `JWT_SECRET`.

## Acceptance checklist
See `docs/auth_acceptance.md` for step-by-step manual verification, including rate limits, role gates, device pairing, and cache-key isolation.
