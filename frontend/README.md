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

Note: The backend exposes both versioned (`/v1`) and unversioned endpoints. The UI targets the unversioned paths by default.

For backend deployment instructions and additional environment variables, consult the [project README](../README.md).
