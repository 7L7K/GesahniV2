import { buildWebSocketUrl } from '@/lib/urls'

const API_URL = process.env.NEXT_PUBLIC_API_ORIGIN || "http://127.0.0.1:8000"

// Build WebSocket URLs dynamically
const WS_URL = buildWebSocketUrl(API_URL, '/v1/ws/care')
const WS_HEALTH_URL = buildWebSocketUrl(API_URL, '/v1/ws/health')

export function getCSPDirectives(): Record<string, string[]> {
    const isDev = process.env.NODE_ENV === 'development'

    if (isDev) {
        return {
            "default-src": ["'self'"],
            "script-src": ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:", "blob:", "https:"],
            "font-src": ["'self'", "data:"],
            "connect-src": [
                "'self'",
                API_URL,
                WS_URL,
                WS_HEALTH_URL
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
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "font-src": ["'self'", "data:"],
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
