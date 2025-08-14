# GesahniV2 Frontend

This directory contains the [Next.js](https://nextjs.org/) web interface for GesahniV2. It provides a browser-based UI that sends prompts to the FastAPI backend and renders responses.

## Prerequisites
- Node.js 20 or newer.
- A running GesahniV2 backend. See the [root README](../README.md) for backend setup and environment configuration.

## Local Development
1. Install dependencies:
   ```bash
   npm install
   ```
2. (Optional) Specify the backend URL if it differs from the default. You can either
   set it in your shell or create a `.env.local` file:
   ```bash
   # Shell
   export NEXT_PUBLIC_API_URL="http://localhost:8000"
   ```
   or
   ```env
   # .env.local
   NEXT_PUBLIC_API_URL="http://localhost:8000"
   ```
   The app falls back to `http://localhost:8000` when this variable is unset.
3. Start the development server:
   ```bash
   npm run dev
   ```
   Visit [http://localhost:3000](http://localhost:3000) to interact with the UI.

## Authentication (Clerk)

This app can use Clerk for authentication. To enable it locally:

1. In your Clerk dashboard, create a Next.js application and retrieve the keys.
2. Add the following to `.env.local` in this directory:

```env
# Clerk keys
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...

# Optional: URL overrides for Clerk (when not deploying on Vercel)
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
```

Notes:
- When keys are present, the app wraps with `ClerkProvider` and shows a minimal header with `Sign in`, `Sign up`, and a `UserButton` when signed in.
- Middleware protects both app routes and `/api/*` routes. Signed-out requests to protected API routes respond with `401`.
- If keys are not set, the app falls back to existing cookie/JWT auth.

Quick test checklist:
- Visit `/` while signed out: you should see Sign in/Sign up in the header and on the homepage.
- Sign in via header. After sign-in, a `UserButton` appears.
- Call `GET /api/protected` while signed out → 401; signed in → 200 JSON with `userId`.

## Production Build & Deployment
Build an optimized production bundle and run it with Node:
```bash
npm run build
npm start
```
You can also deploy the built app with services such as Vercel or any Node.js host.

Run lints locally:
```bash
npm run lint
```

Note: The backend exposes both versioned (`/v1`) and unversioned endpoints. The UI targets versioned endpoints by default and follows redirects for legacy paths.

For backend deployment instructions and additional environment variables, consult the [project README](../README.md).
