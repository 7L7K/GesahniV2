import { buildWebSocketUrl, buildCanonicalWebSocketUrl } from '@/lib/urls'

// Use consistent API_URL logic with proxy mode support
const useDevProxy = ["1", "true", "yes", "on"].includes(String(process.env.NEXT_PUBLIC_USE_DEV_PROXY || process.env.USE_DEV_PROXY || "false").toLowerCase());
const apiOrigin = (process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000").replace(/\/$/, '');
const API_URL = useDevProxy ? '' : apiOrigin;

// Build WebSocket URLs dynamically (only if API_URL is not empty)
const WS_URL = API_URL ? buildWebSocketUrl(API_URL, '/v1/ws/care') : ''
const WS_HEALTH_URL = API_URL ? buildWebSocketUrl(API_URL, '/v1/ws/health') : ''

// Build frontend WebSocket URLs for actual connections (only if API_URL is not empty)
const FRONTEND_WS_URL = API_URL ? buildCanonicalWebSocketUrl(API_URL, '/v1/transcribe') : ''
const FRONTEND_WS_CARE_URL = API_URL ? buildCanonicalWebSocketUrl(API_URL, '/v1/ws/care') : ''
const FRONTEND_WS_HEALTH_URL = API_URL ? buildCanonicalWebSocketUrl(API_URL, '/v1/ws/health') : ''

export function getCSPDirectives(): Record<string, string[]> {
    const isDev = process.env.NODE_ENV === 'development'

    if (isDev) {
        return {
            "default-src": ["'self'"],
            "script-src": ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
            "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            "img-src": ["'self'", "data:", "blob:", "https:"],
            "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
            "connect-src": [
                "'self'",
                ...(API_URL ? [API_URL] : []),
                ...(WS_URL ? [WS_URL] : []),
                ...(WS_HEALTH_URL ? [WS_HEALTH_URL] : []),
                ...(FRONTEND_WS_URL ? [FRONTEND_WS_URL] : []),
                ...(FRONTEND_WS_CARE_URL ? [FRONTEND_WS_CARE_URL] : []),
                ...(FRONTEND_WS_HEALTH_URL ? [FRONTEND_WS_HEALTH_URL] : []),
            ],
            "frame-src": ["'self'"],
            "object-src": ["'none'"],
            "base-uri": ["'self'"],
            "form-action": ["'self'"],
        }
    }

    // Production CSP
    return {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
        "connect-src": [
            "'self'",
            "https://api.gesahni.com",
            "wss://api.gesahni.com",
            "https://*.clerk.accounts.dev",
            "https://*.clerk.com"
        ],
        "frame-src": ["'self'"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }
}

// Generate nonce for production
export function generateNonce(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

// Convert CSP directives to policy string
export function getCSPPolicy(): string {
    const directives = getCSPDirectives();
    const policyParts = Object.entries(directives).map(([key, values]) => {
        return `${key} ${values.join(' ')}`;
    });
    return policyParts.join('; ');
}
