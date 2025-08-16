// Content Security Policy configuration
// Production: strict CSP with nonces
// Development: relaxed CSP for hot reloading

export function getCSPPolicy(nonce?: string): string {
    const isDev = process.env.NODE_ENV === 'development';

    if (isDev) {
        // Development: relaxed CSP for hot reloading and debugging
        return [
            "default-src 'self'",
            "connect-src 'self' http://127.0.0.1:8000 ws://127.0.0.1:8000 http://localhost:8000 ws://localhost:8000",
            "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "frame-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
            "upgrade-insecure-requests"
        ].join("; ");
    }

    // Production: strict CSP with nonces
    const scriptSrc = nonce
        ? `'self' 'nonce-${nonce}'`
        : "'self'";

    return [
        "default-src 'self'",
        "connect-src 'self' https://api.gesahni.com wss://api.gesahni.com", // Production API origins
        `script-src ${scriptSrc}`,
        "style-src 'self' 'unsafe-inline'", // Keep unsafe-inline for CSS-in-JS
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "frame-src 'self'",
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
