/**
 * Auth Orchestrator - Centralized Authentication Authority
 *
 * This is the ONLY component allowed to call /v1/whoami directly.
 * All other components must read authentication state from the global store.
 *
 * Integrates with BootstrapManager to prevent race conditions during auth finish.
 */

// Re-export everything from the modular auth structure
export * from './auth/types';
export * from './auth/core';
export * from './auth/utils';
export * from './auth/events';

// Import resilience utilities
import { fetchWhoamiWithResilience, type WhoamiResponse } from '@/lib/whoamiResilience';

// Legacy exports for backward compatibility
import { AuthOrchestratorImpl } from './auth/core';
export { AuthOrchestratorImpl };

// Extended AuthOrchestrator interface
export interface AuthOrchestrator {
    getCachedIdentity(): WhoamiResponse | null;
    getState(): any;
    subscribe(callback: (state: any) => void): () => void;
    checkAuth(): Promise<void>;
    refreshAuth(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<void>;
    markExplicitStateChange(): void;
    setLogoutInProgress(state: boolean): void;
    handle401Response(): Promise<void>;
    handleRefreshWithRetry(): Promise<void>;
    initialize(): Promise<void>;
    onLoginSuccess(): Promise<void>;
    cleanup(): void;
}

// Singleton instance and factory function
function createOrchestrator(): AuthOrchestratorImpl {
    const instance = new AuthOrchestratorImpl();
    try {
        (globalThis as any).__authOrchestrator = instance;
    } catch {
        // ignore if globalThis not writable (server tests)
    }
    return instance;
}

let orchestratorInstance: AuthOrchestratorImpl = createOrchestrator();

export function getAuthOrchestrator(): AuthOrchestratorImpl & { getCachedIdentity(): WhoamiResponse | null } {
    return orchestratorInstance as AuthOrchestratorImpl & { getCachedIdentity(): WhoamiResponse | null };
}

// Ultra-detailed runtime fence to detect direct whoami calls and auth issues
if (typeof window !== 'undefined') {

    const originalFetch = window.fetch;
    let fetchCallCount = 0;
    let whoamiCallCount = 0;
    let authEndpointCallCount = 0;

    window.fetch = function (...args) {
        const callId = ++fetchCallCount;
        const url = args[0];
        const urlString = typeof url === 'string' ? url : (url as Request)?.url || 'unknown';

        try {
            // Log all API calls for debugging
            if (urlString.includes('/v1/') || urlString.includes('localhost:8000')) {
                const requestInit = args[1] || {};
                const headers = requestInit.headers || {};
                const method = requestInit.method || 'GET';
                const hasAuthHeader = !!(headers as any)['Authorization'];
                const hasCsrfHeader = !!(headers as any)['X-CSRF-Token'];
                const orchestratorMarker = (headers as any)['X-Auth-Orchestrator'];

                // eslint-disable-next-line no-console
                console.log(`🌐 FETCH #${callId}:`, {
                    method,
                    url: urlString,
                    hasAuthHeader,
                    hasCsrfHeader,
                    orchestratorMarker,
                    timestamp: new Date().toISOString()
                });
            }

            if (typeof url === 'string' && (url.includes('/v1/whoami') || url.includes('/v1/auth/whoami'))) {
                whoamiCallCount++;
                // Check if this is a legitimate call from AuthOrchestrator or debug bypass
                const requestInit = args[1] || {};
                const headers = requestInit.headers || {};
                const authHeader = (headers as any)['X-Auth-Orchestrator'];
                const isLegitimateCall = authHeader === 'legitimate' || authHeader === 'debug-bypass' || authHeader === 'booting';

                // Ultra-detailed logging for whoami calls
                // eslint-disable-next-line no-console
                console.groupCollapsed(`👤 WHOAMI CALL #${whoamiCallCount} [${isLegitimateCall ? '✅ LEGITIMATE' : '🚨 DIRECT'}]`);
                // eslint-disable-next-line no-console
                console.log('🔍 CALL DETAILS:', {
                    callId,
                    url: urlString,
                    method: requestInit.method || 'GET',
                    orchestratorMarker: authHeader,
                    isLegitimate: isLegitimateCall,
                    hasAuthHeader: !!(headers as any)['Authorization'],
                    hasCsrfHeader: !!(headers as any)['X-CSRF-Token'],
                    credentials: requestInit.credentials,
                    timestamp: new Date().toISOString()
                });

                // Check orchestrator state
                try {
                    const orch = (globalThis as any).__authOrchestrator;
                    // eslint-disable-next-line no-console
                    console.log('🎭 ORCHESTRATOR STATE:', {
                        exists: !!orch,
                        hasGetState: !!(orch?.getState),
                        hasCheckAuth: !!(orch?.checkAuth),
                        state: orch?.getState?.() || 'unable to get state'
                    });
                } catch (orchError) {
                    // eslint-disable-next-line no-console
                    console.error('🎭 ORCHESTRATOR ERROR:', orchError);
                }

                // eslint-disable-next-line no-console
                console.groupEnd();

                if (!isLegitimateCall) {
                    // Ultra-detailed warning for direct calls
                    // eslint-disable-next-line no-console
                    console.error('🚨🚨🚨 DIRECT /v1/whoami CALL DETECTED! 🚨🚨🚨', {
                        callId,
                        url: urlString,
                        orchestratorMarker: authHeader,
                        stack: new Error().stack,
                        timestamp: new Date().toISOString(),
                        warning: 'This violates the AuthOrchestrator contract. All /v1/whoami calls must go through AuthOrchestrator.checkAuth()',
                        suggestion: 'Use getAuthOrchestrator().checkAuth() instead of direct fetch calls'
                    });
                } else {
                    // eslint-disable-next-line no-console
                    console.info(`✅ LEGITIMATE WHOAMI CALL #${whoamiCallCount}:`, {
                        callId,
                        url: urlString,
                        marker: authHeader,
                        timestamp: new Date().toISOString()
                    });
                }
            }

            // Track auth endpoint calls
            if (typeof url === 'string' && (
                url.includes('/v1/auth/') ||
                url.includes('/login') ||
                url.includes('/logout') ||
                url.includes('/refresh')
            )) {
                authEndpointCallCount++;
                // eslint-disable-next-line no-console
                console.log(`🔐 AUTH ENDPOINT CALL #${authEndpointCallCount}:`, {
                    callId,
                    url: urlString,
                    method: args[1]?.method || 'GET',
                    timestamp: new Date().toISOString()
                });
            }

        } catch (interceptError) {
            // eslint-disable-next-line no-console
            console.error('❌ FETCH INTERCEPTOR ERROR:', interceptError, { callId, url: urlString });
        }

        return originalFetch.apply(this, args as [RequestInfo, RequestInit?]);
    };

    // Add global debugging helpers
    (globalThis as any).debugFetchStats = () => ({
        totalCalls: fetchCallCount,
        whoamiCalls: whoamiCallCount,
        authEndpointCalls: authEndpointCallCount,
        timestamp: new Date().toISOString()
    });

    // eslint-disable-next-line no-console
    console.info('🔧 FETCH INTERCEPTOR ACTIVE: Enhanced logging enabled for all API calls');
}

// Add reset method to the exported function for testing
(getAuthOrchestrator as any).__reset = () => {
    orchestratorInstance = createOrchestrator();
};

export function __resetAuthOrchestrator(): void {
    orchestratorInstance = createOrchestrator();
}
