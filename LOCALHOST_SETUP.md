# Localhost Development Setup

This document describes the centralized localhost configuration for Gesahni development.

## Overview

All development services are configured to use `localhost` consistently instead of `127.0.0.1` or IPv6 addresses. This ensures:

- Consistent URL resolution across browsers and services
- Proper cookie handling and CORS configuration
- Simplified debugging and testing
- Cross-platform compatibility

## Configuration Files

### Backend Configuration (`env.localhost`)

Centralized environment configuration for the backend:

```bash
# Frontend and Backend URLs
APP_URL=http://localhost:3000
API_URL=http://localhost:8000

# CORS Configuration
CORS_ALLOW_ORIGINS=http://localhost:3000

# Server Configuration
HOST=localhost
PORT=8000

# All other services use localhost
OLLAMA_URL=http://localhost:11434
QDRANT_URL=http://localhost:6333
RAGFLOW_URL=http://localhost:8001
TRANSLATE_URL=http://localhost:5000
HOME_ASSISTANT_URL=http://localhost:8123
FALLBACK_RADIO_URL=http://localhost:8000/static/radio.mp3
```

### Frontend Configuration (`frontend/env.localhost`)

Frontend environment template:

```bash
# Next.js public environment variables
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000

# Clerk configuration
CLERK_SIGN_IN_URL=http://localhost:3000/sign-in
CLERK_SIGN_UP_URL=http://localhost:3000/sign-up
CLERK_AFTER_SIGN_IN_URL=http://localhost:3000
CLERK_AFTER_SIGN_UP_URL=http://localhost:3000
```

## Quick Start

### 1. Start Development Environment

```bash
# Start both frontend and backend with localhost configuration
./scripts/dev.sh
```

This will:
- Load centralized configuration from `env.localhost`
- Copy frontend configuration to `frontend/.env.local`
- Start backend on `http://localhost:8000`
- Start frontend on `http://localhost:3000`

### 2. Clear Cookies and Restart Fresh

```bash
# Clear all cookies, cache, and restart fresh
./scripts/clear-cookies.sh
```

This will:
- Stop all running processes
- Clear browser cookies (manual step required)
- Clear local storage files
- Clear build caches
- Restart the development environment

## Manual Cookie Clearing

If you need to manually clear cookies:

1. **Chrome/Edge**:
   - Open DevTools (F12)
   - Go to Application > Storage > Cookies
   - Clear cookies for `localhost:3000` and `localhost:8000`

2. **Firefox**:
   - Open DevTools (F12)
   - Go to Storage > Cookies
   - Clear cookies for `localhost:3000` and `localhost:8000`

3. **Safari**:
   - Preferences > Privacy > Manage Website Data
   - Remove data for `localhost`

## Configuration Details

### Backend Host Binding

The backend is configured to bind to `localhost` only:

```python
# app/main.py
host = os.getenv("HOST", "localhost")
port = int(os.getenv("PORT", "8000"))
```

### Frontend Host Binding

The frontend is configured to bind to `localhost` only:

```json
// package.json
"dev": "next dev -H localhost"
```

### CORS Configuration

CORS is configured to allow only `localhost` origins:

```python
CORS_ALLOW_ORIGINS=http://localhost:3000
```

### URL Helpers

All URL generation uses `localhost` as the default:

```python
# app/url_helpers.py
host = os.getenv("HOST", "localhost")
```

## Troubleshooting

### Port Already in Use

If you get "port already in use" errors:

```bash
# Kill existing processes
pkill -f "uvicorn app.main:app"
pkill -f "next dev"
pkill -f "pnpm dev"

# Or use the clear script
./scripts/clear-cookies.sh
```

### CORS Errors

If you see CORS errors:

1. Ensure you're using `localhost:3000` (not `127.0.0.1:3000`)
2. Clear browser cookies for both domains
3. Restart both frontend and backend

### Authentication Issues

If authentication isn't working:

1. Clear all cookies for `localhost:3000` and `localhost:8000`
2. Ensure Clerk configuration uses `localhost` URLs
3. Restart the development environment

## Environment Variables

### Required for Development

- `NEXT_PUBLIC_API_ORIGIN=http://localhost:8000`
- `NEXT_PUBLIC_SITE_URL=http://localhost:3000`
- `CORS_ALLOW_ORIGINS=http://localhost:3000`
- `HOST=localhost`

### Optional Services

- `OLLAMA_URL=http://localhost:11434` (for local LLM)
- `QDRANT_URL=http://localhost:6333` (for vector store)
- `HOME_ASSISTANT_URL=http://localhost:8123` (for home automation)

## Testing

All tests are configured to use localhost URLs:

```bash
# Run tests
pytest

# Run frontend tests
cd frontend && npm test

# Run load tests
k6 run scripts/k6_load_test.js -e BASE_URL=http://localhost:8000
```

## Security Notes

- Development mode disables secure cookies (`COOKIE_SECURE=0`)
- CORS is configured for localhost only
- No production secrets should be in localhost configuration
- Always use `localhost` instead of `127.0.0.1` for consistency
