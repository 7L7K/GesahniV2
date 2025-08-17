// Content Security Policy configuration
// Production: strict CSP with nonces
// Development: relaxed CSP for hot reloading

export function getCSPPolicy(nonce?: string): string {
    const isDev = process.env.NODE_ENV === 'development';

    if (isDev) {
        // Development: relaxed CSP for hot reloading and debugging
        return [
            "default-src 'self'",
            "connect-src 'self' http://127.0.0.1:8000 ws://127.0.0.1:8000 https://127.0.0.1:3000 http://127.0.0.1:3000 ws://127.0.0.1:3000 wss://127.0.0.1:3000",
            "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://127.0.0.1:3000 http://127.0.0.1:3000 https://*.clerk.accounts.dev https://*.clerk.com",
            "style-src 'self' 'unsafe-inline' https://127.0.0.1:3000 http://127.0.0.1:3000 https://*.clerk.accounts.dev https://*.clerk.com",
            "img-src 'self' data: blob: https://127.0.0.1:3000 http://127.0.0.1:3000 https://*.clerk.accounts.dev https://*.clerk.com",
            "font-src 'self' https://127.0.0.1:3000 http://127.0.0.1:3000 https://*.clerk.accounts.dev https://*.clerk.com",
            "frame-src 'self' https://*.clerk.accounts.dev https://*.clerk.com",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
            "upgrade-insecure-requests"
        ].join("; ");
    }

    // Production: strict CSP with nonces
    const scriptSrc = nonce
        ? `'self' 'nonce-${nonce}' https://*.clerk.accounts.dev https://*.clerk.com`
        : "'self' https://*.clerk.accounts.dev https://*.clerk.com";

    return [
        "default-src 'self'",
        "connect-src 'self' https://api.gesahni.com wss://api.gesahni.com https://*.clerk.accounts.dev https://*.clerk.com", // Production API origins
        `script-src ${scriptSrc}`,
        "style-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev https://*.clerk.com", // Keep unsafe-inline for CSS-in-JS
        "img-src 'self' data: blob: https://*.clerk.accounts.dev https://*.clerk.com",
        "font-src 'self' https://*.clerk.accounts.dev https://*.clerk.com",
        "frame-src 'self' https://*.clerk.accounts.dev https://*.clerk.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
        "upgrade-insecure-requests"
    ].join("; ");
}

// Generate nonce for production
export function generateNonce(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}
