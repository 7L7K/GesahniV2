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
 * Sanitize a next parameter to prevent open redirects
 * @param raw - Raw next parameter
 * @param fallback - Fallback path if invalid
 * @returns Sanitized path
 */
export function sanitizeNextPath(raw: string | null | undefined, fallback: string = '/'): string {
    const input = (raw || '').trim();
    if (!input) return fallback;

    // Reject absolute URLs to prevent open redirects
    // This regex matches URLs with protocol (http:, https:, etc.) followed by //
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(input)) return fallback;

    // Reject protocol-relative URLs (starting with // but not ///)
    if (input.startsWith('//') && !input.startsWith('///')) return fallback;

    // Normalize multiple slashes to single slash first
    const normalized = input.replace(/\/+/g, '/');

    // Ensure path starts with /
    if (!normalized.startsWith('/')) return fallback;

    return normalized;
}
