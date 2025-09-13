/**
 * INTERNAL MODULE - Whoami Resilience Utilities
 *
 * This module provides low-level whoami fetching with retry/backoff.
 * ONLY the AuthOrchestrator should import this module.
 */

// Development warning for incorrect imports
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    // Get the current stack to see who's importing us
    const stack = new Error().stack || '';
    const isImportedByAuthService = stack.includes('/services/auth/') || stack.includes('authOrchestrator');

    if (!isImportedByAuthService) {
        console.warn('⚠️  whoamiResilience.ts imported outside auth services!');
        console.warn('This module should only be used by AuthOrchestrator.');
        console.warn('Use getAuthOrchestrator().checkAuth() instead.');
    }
}

export interface WhoamiResponse {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
    email?: string | null;
    source?: string;
}

/**
 * Fetch whoami with resilience (retry/backoff)
 * INTERNAL USE ONLY - for AuthOrchestrator
 */
export async function fetchWhoamiWithResilience(): Promise<WhoamiResponse> {
    const MAX_RETRIES = 3;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        try {
            // Debug: mark whoami request
            try {
                const { logAuth } = await import('@/auth/debug');
                logAuth('WHOAMI_REQUEST');
            } catch { /* noop */ }

            const response = await rawWhoamiFetch();

            // Debug: log response status
            try {
                const { logAuth } = await import('@/auth/debug');
                logAuth('WHOAMI_RESPONSE', { ok: response.ok, status: response.status });
            } catch { /* noop */ }

            if (response.ok) {
                const data = await response.json();
                try {
                    const { logAuth } = await import('@/auth/debug');
                    const userId = (data && data.user && data.user.id) ? true : false;
                    logAuth('WHOAMI_USER', { user: userId });
                } catch { /* noop */ }
                return data;
            }

            // Distinguish error classes for orchestrator/backoff
            if (response.status === 404) {
                throw new Error('WHOAMI_404_NotFound');
            }
            if (response.status === 401) {
                throw new Error('WHOAMI_401_Unauthorized');
            }
            if (response.status >= 500) {
                // Server error - retry
                throw new Error(`WHOAMI_5xx_ServerError_${response.status}`);
            }
            // Other client errors (4xx) - don't retry
            throw new Error(`WHOAMI_4xx_ClientError_${response.status}`);
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));

            // Only retry on server errors and network failures
            const msg = lastError.message || '';
            const shouldRetry = /5xx|ServerError|NetworkError|TypeError/i.test(msg);
            if (attempt < MAX_RETRIES - 1 && shouldRetry) {
                // Calculate incremental backoff
                const backoffMs = (attempt + 1) * 500; // 500ms, 1000ms, 1500ms
                console.debug(`WhoamiResilience: Retry ${attempt + 1} after ${backoffMs}ms`, {
                    error: lastError.message
                });
                await delay(backoffMs);
            }
        }
    }

    throw lastError || new Error('Whoami fetch failed after retries');
}

/**
 * Raw whoami fetch using apiFetch with proper credentials and CSRF
 * PRIVATE - internal to this module only
 */
async function rawWhoamiFetch(): Promise<Response> {
    // Import apiFetch dynamically to avoid circular dependencies
    const { apiFetch } = await import('@/lib/api/fetch');
    return apiFetch('/v1/whoami', {
        method: 'GET',
        credentials: 'include',
        headers: {
            'Accept': 'application/json',
            'X-Auth-Orchestrator': 'legitimate', // Mark as legitimate call
        },
    });
}

/**
 * Utility delay function
 */
function delay(ms: number): Promise<void> {
    return new Promise(resolve => {
        if (typeof jest !== 'undefined') {
            // Use Jest's fake timer delay in tests
            setTimeout(resolve, ms);
        } else {
            // Use real setTimeout in production
            setTimeout(resolve, ms);
        }
    });
}
