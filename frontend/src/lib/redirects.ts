/**
 * Frontend redirect utilities that mirror backend rules.
 *
 * This module provides redirect safety utilities that enforce:
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
    '/v1/csrf',
    '/google',
    '/oauth',
    '/sign-in',
    '/sign-up'
]);

// Default fallback path
export const DEFAULT_REDIRECT = '/dashboard';

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

export function sanitizeNextPath(rawPath: string | null | undefined): string {
    if (!rawPath || typeof rawPath !== 'string') {
        return DEFAULT_REDIRECT;
    }

    let path = rawPath.trim();
    if (!path) return DEFAULT_REDIRECT;

    try {
        // Step 1: Safe URL decoding (at most twice)
        path = safeDecodeUrl(path, 2);

        // Step 2: Reject absolute URLs to prevent open redirects
        if (path.startsWith('http://') || path.startsWith('https://')) {
            console.warn('Rejected absolute URL redirect:', path);
            return DEFAULT_REDIRECT;
        }

        // Step 3: Reject protocol-relative URLs (starting with // but not ///)
        if (path.startsWith('//') && !path.startsWith('///')) {
            console.warn('Rejected protocol-relative URL redirect:', path);
            return DEFAULT_REDIRECT;
        }

        // Step 4: Ensure path starts with /
        if (!path.startsWith('/')) {
            console.warn('Rejected non-relative path redirect:', path);
            return DEFAULT_REDIRECT;
        }

        // Step 4.1: Reject obvious local filesystem paths or file downloads
        const lower = path.toLowerCase();
        if (/^\/(var|etc|usr|private|system|library|applications|volumes)\b/.test(lower)) {
            console.warn('Rejected filesystem-like redirect path:', path);
            return DEFAULT_REDIRECT;
        }
        if (/\.(png|jpe?g|gif|webp|svg|pdf|zip|dmg|mov|mp4|mp3|wav|heic|heif)(?:[?#].*)?$/i.test(path)) {
            console.warn('Rejected file-like redirect path:', path);
            return DEFAULT_REDIRECT;
        }
        if (/[\s:]/.test(path)) {
            console.warn('Rejected suspicious redirect path with spaces/colon:', path);
            return DEFAULT_REDIRECT;
        }

        // Step 5: Strip fragments (#...)
        if (path.includes('#')) {
            path = path.split('#')[0];
        }

        // Step 6: Remove any nested ?next=... parameters
        if (path.includes('?')) {
            try {
                const url = new URL(path, 'http://localhost'); // Dummy base for parsing
                url.searchParams.delete('next');
                path = url.pathname + (url.search ? url.search : '');
            } catch {
                // If URL parsing fails, continue with original path
            }
        }

        // Step 7: Prevent redirect loops by blocking auth-related paths
        if (isAuthPath(path)) {
            console.warn('Rejected auth path redirect:', path);
            return DEFAULT_REDIRECT;
        }

        // Step 8: Normalize redundant slashes
        path = path.replace(/\/+/g, '/');

        // Step 9: Basic path validation (no .. traversal)
        if (path.includes('..')) {
            console.warn('Rejected path traversal redirect:', path);
            return DEFAULT_REDIRECT;
        }

        return path;

    } catch (e) {
        console.error('Error sanitizing redirect path', rawPath, e);
        return DEFAULT_REDIRECT;
    }
}

// Helper function to capture next path to backend gs_next cookie
export async function captureNextPathToBackend(nextPath: string): Promise<void> {
    if (!nextPath || nextPath === DEFAULT_REDIRECT) {
        return;
    }

    try {
        // Import apiFetch dynamically to avoid circular dependencies
        const { apiFetch } = await import('@/lib/api');

        // Make a fire-and-forget POST to the backend login endpoint
        // This sets the gs_next cookie on the backend for post-login redirect
        const response = await apiFetch('/v1/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: '__capture_next__', // pragma: allowlist secret - Special marker for next path capture
                password: '__capture_next__', // pragma: allowlist secret
                next: nextPath,
            }),
        });

        if (!response.ok) {
            console.warn('Failed to capture next path to backend:', response.status);
        }
    } catch (error) {
        console.warn('Error capturing next path to backend:', error);
    }
}
