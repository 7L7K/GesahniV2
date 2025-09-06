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
    refreshAuth(): Promise<void>;
    markExplicitStateChange(): void;
    handle401Response(): Promise<void>;
    handleRefreshWithRetry(): Promise<void>;
    initialize(): Promise<void>;
    cleanup(): void;
}

// Singleton instance and factory function
let orchestratorInstance: AuthOrchestratorImpl | null = null;

export function getAuthOrchestrator(): AuthOrchestratorImpl & { getCachedIdentity(): WhoamiResponse | null } {
    if (!orchestratorInstance) {
        orchestratorInstance = new AuthOrchestratorImpl();
    }
    return orchestratorInstance as AuthOrchestratorImpl & { getCachedIdentity(): WhoamiResponse | null };
}

// Runtime fence to detect direct whoami calls
if (typeof window !== 'undefined') {

    const originalFetch = window.fetch;
    window.fetch = function (...args) {
        const url = args[0];
        if (typeof url === 'string' && url.includes('/v1/whoami')) {
            // Check if this is a legitimate call from AuthOrchestrator or debug bypass
            const requestInit = args[1] || {};
            const headers = requestInit.headers || {};
            const authHeader = (headers as any)['X-Auth-Orchestrator'];
            const isLegitimateCall = authHeader === 'legitimate' || authHeader === 'debug-bypass';

            if (!isLegitimateCall) {
                // This is a direct call to /v1/whoami outside of AuthOrchestrator!
                const isDev = process.env.NODE_ENV === 'development' || process.env.NODE_ENV === 'test';

                console.error('🚨 DIRECT /v1/whoami CALL DETECTED! 🚨');
                console.error('This violates the AuthOrchestrator contract.');
                console.error('All /v1/whoami calls must go through AuthOrchestrator.');
                console.error('Use getAuthOrchestrator().checkAuth() instead.');
                console.error('Stack trace:', new Error().stack);

                // In development/test, throw an error to catch this immediately
                if (isDev) {
                    throw new Error('Direct whoami call detected! Use AuthOrchestrator instead.');
                } else {
                    // In production, log the violation but allow it to proceed
                    // This helps with monitoring without breaking existing functionality
                    console.warn('🚨 PRODUCTION: Direct whoami call allowed but logged for monitoring');
                }
            }
        }
        return originalFetch.apply(this, args as [RequestInfo, RequestInit?]);
    };
}

// Add reset method to the exported function for testing
(getAuthOrchestrator as any).__reset = () => {
    orchestratorInstance = null;
};

export function __resetAuthOrchestrator(): void {
    orchestratorInstance = null;
}
