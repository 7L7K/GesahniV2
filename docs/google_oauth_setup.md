Google OAuth setup (Quick reference)

1) Where to find Client ID / Secret
- Open Google Cloud Console → APIs & Services → OAuth consent screen and Credentials.
- Create an OAuth 2.0 Client ID (type: Web application).
- Copy the Client ID and Client Secret.

2) What to paste where
- Backend (.env):
  - `GOOGLE_CLIENT_ID` = Client ID
  - `GOOGLE_CLIENT_SECRET` = Client Secret
  - `GOOGLE_REDIRECT_URI` = e.g. `http://localhost:8000/v1/google/auth/callback`

- Frontend (optional `frontend/.env.local`):
  - `NEXT_PUBLIC_GOOGLE_CLIENT_ID` = Client ID (only if using a client-side Google SDK)

3) Authorized redirect URIs to register in Google Cloud Console
- http://localhost:8000/v1/google/auth/callback   (backend canonical callback)
- https://your-production-host.example.com/v1/google/auth/callback

Notes:
- The backend expects `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` and performs the
  authorization code exchange server-side. The frontend calls `/v1/google/auth/login_url`
  to retrieve a server-generated auth URL and relies on short-lived CSRF cookies.
- `NEXT_PUBLIC_*` variables are injected at build time and are accessible to browser code.
  Never place secrets (client secret, tokens) in `NEXT_PUBLIC_*`.

