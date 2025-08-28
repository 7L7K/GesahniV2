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
   export NEXT_PUBLIC_API_ORIGIN="http://localhost:8000"
   ```
   or
   ```env
   # .env.local
   NEXT_PUBLIC_API_ORIGIN="http://localhost:8000"
   ```
   The app defaults to `http://localhost:8000` for consistent localhost naming.
   Visit [http://localhost:3000](http://localhost:3000) to interact with the UI.
3. Start the development server:
   ```bash
   npm run dev
   ```
   Visit [http://localhost:3000](http://localhost:3000) to interact with the UI.

## Authentication

Clerk has been removed. The frontend now uses the backend’s cookie/JWT or header-token flow exclusively.

Supported modes:
- Cookie/JWT via backend sessions (default)
- Header-based tokens when `NEXT_PUBLIC_HEADER_AUTH_MODE=1`

Google OAuth is initiated from the Login page and completed by the backend, which then redirects back with tokens when in header mode.

Quick test checklist:
- Visit `/login` while signed out and sign in via Google or username/password.
- After login, the header shows “Logout”, and protected views load normally.

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
