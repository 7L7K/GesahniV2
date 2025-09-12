/**
 * Centralized URL utilities for building URLs from request context
 * Avoids hardcoding http://localhost:3000 and other URLs
 */

/**
 * Get the canonical frontend origin for WebSocket URL building
 * @returns Canonical frontend origin (http://localhost:3000)
 */
export function getCanonicalFrontendOrigin(): string {
    // Use the same canonical origin as the backend expects
    // This ensures consistency between frontend and backend origin validation
    return "http://localhost:3000";
}

/**
 * Build a URL from the current request's nextUrl
 * @param req - NextRequest object
 * @param pathname - Target pathname (defaults to '/')
 * @param searchParams - Optional search parameters
 * @returns URL object
 */
export function buildUrlFromRequest(
    req: Request,
    pathname: string = '/',
    searchParams?: Record<string, string>
): URL {
    const url = new URL(req.url);
    url.pathname = pathname;

    if (searchParams) {
        Object.entries(searchParams).forEach(([key, value]) => {
            url.searchParams.set(key, value);
        });
    }

    return url;
}

/**
 * Build a redirect URL from the current request's nextUrl
 * @param req - NextRequest object
 * @param pathname - Target pathname
 * @param searchParams - Optional search parameters
 * @returns URL object for redirects
 */
export function buildRedirectUrl(
    req: Request,
    pathname: string,
    searchParams?: Record<string, string>
): URL {
    return buildUrlFromRequest(req, pathname, searchParams);
}

/**
 * Get the base URL for the current request
 * @param req - NextRequest object
 * @returns Base URL string
 */
export function getBaseUrl(req: Request): string {
    const url = new URL(req.url);
    return `${url.protocol}//${url.host}`;
}

/**
 * Build a relative URL for Clerk auth endpoints
 * @param pathname - Auth pathname (e.g., '/sign-in', '/sign-up')
 * @param next - Optional redirect path
 * @returns Relative URL string
 */
export function buildAuthUrl(pathname: string, next?: string): string {
    const url = new URL(pathname, 'http://localhost'); // Dummy base for relative URL
    if (next) {
        url.searchParams.set('next', next);
    }
    return url.pathname + url.search;
}

/**
 * Build a WebSocket URL from the API origin
 * @param apiOrigin - API origin (e.g., 'http://localhost:8000')
 * @param path - WebSocket path
 * @returns WebSocket URL
 */
export function buildWebSocketUrl(apiOrigin: string, path: string): string {
    const parsed = new URL(apiOrigin);
    const wsScheme = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = `${wsScheme}//${parsed.host}`;

    // Ensure path starts with / and join properly
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${wsBase}${normalizedPath}`;
}

/**
 * Build a WebSocket URL using the canonical frontend origin for consistent origin validation
 * @param apiOrigin - API origin (e.g., 'http://localhost:8000')
 * @param path - WebSocket path
 * @returns WebSocket URL
 */
export function buildCanonicalWebSocketUrl(apiOrigin: string, path: string): string {
    // Use the API origin for WebSocket connections, not frontend origin
    const parsed = new URL(apiOrigin);
    const wsScheme = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = `${wsScheme}//${parsed.host}`;

    // Ensure path starts with / and join properly
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${wsBase}${normalizedPath}`;
}

/**
 * Safe next path helper: allow only relative paths not matching /login|/signup; if invalid, return '/'
 * @param raw - Raw next parameter
 * @returns Sanitized path or '/'
 */
export function safeNext(raw: string | null | undefined): string {
    return sanitizeNextPath(raw, '/');
}

/**
 * Sanitize a next parameter to prevent open redirects
 * @param raw - Raw next parameter
 * @param fallback - Fallback path if invalid
 * @returns Sanitized path
 */
export function sanitizeNextPath(raw: string | null | undefined, fallback: string = '/'): string {
    const input = (raw || '').trim();
    if (!input) return fallback;

    // URL-decode the input multiple times to handle nested encoding
    // Double-decoding is bounded to prevent infinite loops from malicious input
    // that could contain nested encoding layers (e.g., %2520 = %20 encoded again).
    // We limit to 5 decodes as sufficient for legitimate use while preventing DoS
    // from attackers creating deeply nested encodings.
    let decodedInput: string = input;
    let previousDecoded: string = input;

    try {
        // Decode up to 5 levels deep to prevent infinite loops from malicious input
        for (let i = 0; i < 5; i++) {
            previousDecoded = decodedInput;
            decodedInput = decodeURIComponent(decodedInput);

            // Stop if decoding didn't change anything (no more encoding layers)
            if (decodedInput === previousDecoded) {
                break;
            }
        }
    } catch {
        // If decoding fails at any point, use the last successfully decoded version
        decodedInput = previousDecoded || input;
    }

    // Reject absolute URLs to prevent open redirects
    // Absolute URLs (http://, https://) are rejected because they could redirect
    // users to external malicious domains, enabling phishing attacks. Only
    // same-origin relative paths are allowed for security.
    // This regex matches URLs with protocol (http:, https:, etc.) followed by //
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(decodedInput)) return fallback;

    // Reject protocol-relative URLs (starting with // but not ///)
    // Protocol-relative URLs (//domain.com) are rejected because they inherit
    // the current page's protocol (http/https) but allow redirecting to any domain.
    // This prevents attackers from redirecting users to malicious sites while
    // maintaining the appearance of staying on the same protocol.
    if (decodedInput.startsWith('//') && !decodedInput.startsWith('///')) return fallback;

    // Prevent redirect loops by blocking login-related paths
    // Auth paths (/login, /sign-in, /sign-up) are blocklisted to prevent
    // infinite redirect loops. If users were redirected to login pages after login,
    // they would be caught in a cycle of login → redirect to login → login...
    // This ensures post-authentication redirects go to legitimate application pages.
    if (decodedInput.includes('/login') || decodedInput.includes('/sign-in') || decodedInput.includes('/sign-up')) {
        return fallback;
    }

    // Normalize multiple slashes to single slash first
    const normalized = decodedInput.replace(/\/+/g, '/');

    // Ensure path starts with /
    if (!normalized.startsWith('/')) return fallback;

    return normalized;
}
