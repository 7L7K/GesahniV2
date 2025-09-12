/**
 * Unified redirect utilities for safe, single-decode redirects.
 *
 * This module provides canonical redirect safety utilities that enforce:
 * - Single-decode enforcement (decode at most twice)
 * - Prevention of auth page redirects
 * - Same-origin relative paths only
 * - Strip fragments (#...), collapse //, remove nested ?next=...
 * - gs_next cookie support for post-login targets
 */

// Auth paths that should never be redirected to
const AUTH_PATHS = new Set([
    '/login',
    '/v1/auth/login',
    '/v1/auth/logout',
    '/v1/auth/refresh',
    '/v1/auth/csrf',
    '/google',
    '/oauth',
    '/sign-in',
    '/sign-up'
]);

// Default fallback path
export const DEFAULT_FALLBACK = '/dashboard';

export function isAuthPath(path: string): boolean {
    if (!path) return false;

    // Check exact matches
    if (AUTH_PATHS.has(path)) return true;

    // Check if path contains auth patterns
    for (const authPath of AUTH_PATHS) {
        if (path.includes(authPath)) return true;
    }

    return false;
}

export function safeDecodeUrl(url: string, maxDecodes: number = 2): string {
    let decoded = url;
    let previous = url;

    for (let i = 0; i < maxDecodes; i++) {
        try {
            previous = decoded;
            decoded = decodeURIComponent(decoded);

            // Stop if no change (no more encoding layers)
            if (decoded === previous) {
                break;
            }
        } catch {
            // If decoding fails at any point, use the last successfully decoded version
            decoded = previous;
            break;
        }
    }

    return decoded;
}

export function sanitizeRedirectPath(
    rawPath: string | null | undefined,
    fallback: string = DEFAULT_FALLBACK
): string {
    if (!rawPath || typeof rawPath !== 'string') {
        return fallback;
    }

    let path = rawPath.trim();
    if (!path) return fallback;

    try {
        // Step 1: Safe URL decoding (at most twice)
        path = safeDecodeUrl(path, 2);

        // Step 2: Reject absolute URLs to prevent open redirects
        if (path.startsWith('http://') || path.startsWith('https://')) {
            console.warn('Rejected absolute URL redirect:', path);
            return fallback;
        }

        // Step 3: Reject protocol-relative URLs (starting with // but not ///)
        if (path.startsWith('//') && !path.startsWith('///')) {
            console.warn('Rejected protocol-relative URL redirect:', path);
            return fallback;
        }

        // Step 4: Ensure path starts with /
        if (!path.startsWith('/')) {
            console.warn('Rejected non-relative path redirect:', path);
            return fallback;
        }

        // Step 5: Strip fragments (#...)
        if (path.includes('#')) {
            path = path.split('#')[0];
        }

        // Step 6: Remove any nested ?next=... parameters
        if (path.includes('?')) {
            const url = new URL(path, 'http://localhost'); // Dummy base for parsing
            url.searchParams.delete('next');
            path = url.pathname + (url.search ? url.search : '');
        }

        // Step 7: Prevent redirect loops by blocking auth-related paths
        if (isAuthPath(path)) {
            console.warn('Rejected auth path redirect:', path);
            return fallback;
        }

        // Step 8: Normalize redundant slashes
        path = path.replace(/\/+/g, '/');

        // Step 9: Basic path validation (no .. traversal)
        if (path.includes('..')) {
            console.warn('Rejected path traversal redirect:', path);
            return fallback;
        }

        return path;

    } catch (e) {
        console.error('Error sanitizing redirect path', rawPath, e);
        return fallback;
    }
}

export function safeNext(raw: string | null | undefined): string {
    return sanitizeRedirectPath(raw, DEFAULT_FALLBACK);
}

export function getSafeRedirectTarget(
    nextParam?: string | null,
    gsNextCookie?: string | null,
    fallback: string = DEFAULT_FALLBACK
): string {
    // Priority 1: Explicit next parameter
    if (nextParam) {
        const sanitized = sanitizeRedirectPath(nextParam, fallback);
        if (sanitized !== fallback) { // Only use if it wasn't rejected
            return sanitized;
        }
    }

    // Priority 2: gs_next cookie for post-login targets
    if (gsNextCookie) {
        const sanitized = sanitizeRedirectPath(gsNextCookie, fallback);
        if (sanitized !== fallback) { // Only use if it wasn't rejected
            // Clear the cookie after use
            clearGsNextCookie();
            return sanitized;
        }
    }

    // Priority 3: Fallback
    return fallback;
}

export function setGsNextCookie(path: string, ttlSeconds: number = 300): void {
    if (!path || !path.startsWith('/')) {
        console.warn('Invalid gs_next path:', path);
        return;
    }

    try {
        // Calculate expiration
        const expires = new Date();
        expires.setSeconds(expires.getSeconds() + ttlSeconds);

        // Set cookie with security flags
        document.cookie = `gs_next=${encodeURIComponent(path)}; expires=${expires.toUTCString()}; path=/; SameSite=Lax; Secure`;

        console.debug('Set gs_next cookie:', path);
    } catch (e) {
        console.error('Failed to set gs_next cookie:', e);
    }
}

export function getGsNextCookie(): string | null {
    try {
        const cookies = document.cookie.split(';');
        for (const cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'gs_next' && value) {
                return decodeURIComponent(value);
            }
        }
    } catch (e) {
        console.error('Failed to get gs_next cookie:', e);
    }
    return null;
}

export function clearGsNextCookie(): void {
    try {
        // Clear cookie by setting expiration to past date
        document.cookie = 'gs_next=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax; Secure';
        console.debug('Cleared gs_next cookie');
    } catch (e) {
        console.error('Failed to clear gs_next cookie:', e);
    }
}

export function buildOriginAwareRedirectUrl(path: string): string {
    if (!path.startsWith('/')) {
        throw new Error('Path must start with / for security');
    }

    try {
        // Use current origin for redirects
        const origin = window.location.origin;
        return `${origin}${path}`;
    } catch (e) {
        console.error('Error building origin-aware redirect URL:', e);
        // Fallback to localhost for development
        return `http://localhost:3000${path}`;
    }
}
