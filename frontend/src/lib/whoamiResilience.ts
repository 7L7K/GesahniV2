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
            const response = await rawWhoamiFetch();

            if (response.ok) {
                return await response.json();
            } else if (response.status >= 500) {
                // Server error - retry
                throw new Error(`Server error: ${response.status}`);
            } else {
                // Client error (4xx) - don't retry
                throw new Error(`Client error: ${response.status}`);
            }
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));

            if (attempt < MAX_RETRIES - 1) {
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
 * Raw whoami fetch using direct fetch
 * PRIVATE - internal to this module only
 */
async function rawWhoamiFetch(): Promise<Response> {
    const url = '/v1/whoami';
    return fetch(url, {
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
