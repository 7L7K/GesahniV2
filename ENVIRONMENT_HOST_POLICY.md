# Environment & Host Policy

This document outlines the standardized environment and host policy for GesahniV2 to ensure consistent and secure configuration across all components.

## Policy Summary

### Frontend Canonical URL
- **URL**: `http://localhost:3000`
- **Purpose**: Single frontend origin for all client-side applications
- **Usage**: CORS origins, CSRF tokens, cookies, OAuth callbacks

### Backend Canonical URL
- **URL**: `http://127.0.0.1:8000`
- **Purpose**: API server with IPv4 consistency to avoid dual-stack surprises
- **Usage**: All API calls, WebSocket connections, metrics endpoints

## Implementation Details

### Environment Variables

#### Backend Configuration
```bash
# Single frontend origin for CORS - use exactly one origin
CORS_ALLOW_ORIGINS=http://localhost:3000

# Backend URL for internal services
FALLBACK_RADIO_URL=http://127.0.0.1:8000/static/radio.mp3
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/google/oauth/callback
```

#### Frontend Configuration
```bash
# Frontend canonical URL
NEXT_PUBLIC_SITE_URL=http://localhost:3000
APP_URL=http://localhost:3000

# Backend API origin (IPv4 for consistency)
NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000
```

### Security Benefits

1. **CORS Consistency**: Single frontend origin prevents CORS misconfiguration
2. **IPv4 Backend**: Avoids dual-stack IPv4/IPv6 resolution surprises
3. **OAuth Security**: Consistent callback URLs prevent auth bypass
4. **Cookie Security**: Single domain for secure cookie handling
5. **CSRF Protection**: Predictable origin validation

### Files Updated

#### Environment Files
- `env.example` - Updated FALLBACK_RADIO_URL to use 127.0.0.1:8000
- `env.consolidated` - Updated CORS_ALLOW_ORIGINS and APP_URL

#### Frontend Configuration
- `frontend/src/lib/csp.ts` - Removed hardcoded localhost:3000 from CSP
- `frontend/package.json` - Already correctly configured

#### Backend Configuration
- `app/main.py` - Already correctly configured with single CORS origin

#### Test Files
- `test_complete_auth_flow.py` - Updated frontend URL and Origin headers
- `test_auth_flow.py` - Updated frontend URL
- `test_browser_auth.py` - Updated frontend URL
- `scripts/test_network.sh` - Updated frontend URL and Origin headers
- `scripts/test_runtime_receipts.sh` - Updated frontend URL and Origin headers
- `test_curl_matrix.sh` - Updated backend URL to 127.0.0.1:8000

#### Documentation
- `README.md` - Updated backend URL references
- `COOKIE_AUTH_SETUP.md` - Updated CORS origins and frontend URL
- `docs/auth_acceptance.md` - Updated frontend URL
- `docs/README-auth.md` - Updated frontend URL references
- `frontend/src/app/test-cors/page.tsx` - Updated frontend URL reference

#### Development Scripts
- `scripts/dev.sh` - Updated frontend URL references

### Validation

To verify the policy is correctly implemented:

1. **CORS Test**: Ensure only `http://localhost:3000` is in CORS_ALLOW_ORIGINS
2. **API Calls**: Verify all frontend API calls go to `http://127.0.0.1:8000`
3. **OAuth**: Confirm Google OAuth callback uses `http://127.0.0.1:8000`
4. **Cookies**: Verify cookies are set for `localhost:3000` domain
5. **WebSocket**: Confirm WebSocket connections use `ws://127.0.0.1:8000`

### Migration Notes

- All existing configurations have been updated to follow this policy
- No breaking changes for existing functionality
- Improved security through consistent origin validation
- Better IPv4/IPv6 compatibility for backend services

This policy ensures a secure, consistent, and predictable environment configuration across all GesahniV2 components.
