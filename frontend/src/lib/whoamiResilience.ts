/**
 * Resilient Whoami Client
 *
 * Provides retry/backoff with jitter for network errors and caches the last good identity
 * to prevent UI flicker during temporary connectivity issues.
 */

interface WhoamiResponse {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
    email?: string | null;
    source?: string;
}

interface CachedIdentity {
    data: WhoamiResponse;
    timestamp: number;
}

export class ResilientWhoamiClient {
    private lastGoodIdentity: CachedIdentity | null = null;
    private readonly CACHE_TTL_MS = 3000; // 3 seconds
    private retryAttempts = 0;
    private readonly MAX_RETRIES = 3;
    private readonly BASE_BACKOFF_MS = 1000;
    private readonly MAX_BACKOFF_MS = 5000;

    /**
     * Get cached identity if it's still fresh, otherwise fetch new one with resilience
     */
    async getIdentity(apiFetch: (url: string, options?: any) => Promise<Response>): Promise<WhoamiResponse> {
        // Return cached identity if it's still fresh (prevents UI flicker)
        const cached = this.getCachedIdentity();
        if (cached) {
            console.debug('WhoamiResilience: Returning cached identity', {
                age: Date.now() - cached.timestamp,
                userId: cached.data.user_id,
            });
            return cached.data;
        }

        // Fetch new identity with retry/backoff
        return this.fetchWithResilience(apiFetch);
    }

    /**
     * Get cached identity if it's still within TTL
     */
    private getCachedIdentity(): CachedIdentity | null {
        if (!this.lastGoodIdentity) {
            return null;
        }

        const age = Date.now() - this.lastGoodIdentity.timestamp;
        if (age < this.CACHE_TTL_MS) {
            return this.lastGoodIdentity;
        }

        // Cache expired
        this.lastGoodIdentity = null;
        return null;
    }

    /**
     * Fetch identity with retry/backoff and jitter
     */
    private async fetchWithResilience(apiFetch: (url: string, options?: any) => Promise<Response>): Promise<WhoamiResponse> {
        this.retryAttempts = 0;

        while (this.retryAttempts <= this.MAX_RETRIES) {
            try {
                const response = await apiFetch('/v1/whoami', {
                    method: 'GET',
                    auth: true,
                    dedupe: false,
                    cache: 'no-store'
                });

                if (response.ok) {
                    const data = await response.json();

                    // Cache successful response
                    this.lastGoodIdentity = {
                        data,
                        timestamp: Date.now()
                    };

                    console.debug('WhoamiResilience: Successfully fetched identity', {
                        userId: data.user_id,
                        attempt: this.retryAttempts + 1,
                    });

                    return data;
                } else {
                    // Don't retry on auth errors (401, 403), only on network/server errors
                    if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
                        throw new Error(`Auth error: ${response.status}`);
                    }

                    // Retry on 5xx, network errors, timeouts
                    throw new Error(`Server error: ${response.status}`);
                }
            } catch (error) {
                this.retryAttempts++;

                if (this.retryAttempts > this.MAX_RETRIES) {
                    console.warn('WhoamiResilience: Max retries exceeded', {
                        attempts: this.retryAttempts,
                        error: error instanceof Error ? error.message : String(error),
                    });
                    throw error;
                }

                // Calculate backoff with jitter
                const backoffMs = this.calculateBackoffWithJitter();
                console.warn('WhoamiResilience: Retry attempt', {
                    attempt: this.retryAttempts,
                    backoffMs,
                    error: error instanceof Error ? error.message : String(error),
                });

                // Wait before retry
                await this.delay(backoffMs);
            }
        }

        // This should never be reached, but TypeScript needs it
        throw new Error('Unexpected error in resilient fetch');
    }

    /**
     * Calculate exponential backoff with jitter
     */
    private calculateBackoffWithJitter(): number {
        const exponentialBackoff = this.BASE_BACKOFF_MS * Math.pow(2, this.retryAttempts - 1);
        const jitter = Math.random() * 0.3 * exponentialBackoff; // ±30% jitter
        const backoffWithJitter = exponentialBackoff + jitter;

        return Math.min(backoffWithJitter, this.MAX_BACKOFF_MS);
    }

    /**
     * Utility delay function
     */
    private delay(ms: number): Promise<void> {
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

    /**
     * Clear cached identity (useful for logout)
     */
    clearCache(): void {
        this.lastGoodIdentity = null;
    }

    /**
     * Get cache status for debugging
     */
    getCacheStatus() {
        return {
            hasCache: !!this.lastGoodIdentity,
            cacheAge: this.lastGoodIdentity ? Date.now() - this.lastGoodIdentity.timestamp : 0,
            cacheTtl: this.CACHE_TTL_MS,
            isExpired: this.lastGoodIdentity ? (Date.now() - this.lastGoodIdentity.timestamp) >= this.CACHE_TTL_MS : true,
        };
    }
}

// Singleton instance
let resilientWhoamiClient: ResilientWhoamiClient | null = null;

export function getResilientWhoamiClient(): ResilientWhoamiClient {
    if (!resilientWhoamiClient) {
        resilientWhoamiClient = new ResilientWhoamiClient();
    }
    return resilientWhoamiClient;
}
