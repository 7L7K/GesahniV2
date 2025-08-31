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

// Legacy exports for backward compatibility
import { AuthOrchestratorImpl } from './auth/core';
export { AuthOrchestratorImpl };

// Singleton instance and factory function
let orchestratorInstance: AuthOrchestratorImpl | null = null;

export function getAuthOrchestrator(): AuthOrchestratorImpl {
    if (!orchestratorInstance) {
        orchestratorInstance = new AuthOrchestratorImpl();
    }
    return orchestratorInstance;
}

// Development helper to detect direct whoami calls
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    // Track legitimate whoami calls from AuthOrchestrator
    const legitimateWhoamiCalls = new Set<number>();
    let callIdCounter = 0;

    // Mark legitimate calls from AuthOrchestrator
    const markLegitimateCall = () => {
        const callId = ++callIdCounter;
        legitimateWhoamiCalls.add(callId);

        // Clean up the call ID after a short delay
        setTimeout(() => {
            legitimateWhoamiCalls.delete(callId);
        }, 1000);

        return callId;
    };

    const originalCheckAuth = AuthOrchestratorImpl.prototype.checkAuth;
    AuthOrchestratorImpl.prototype.checkAuth = async function (...args: any[]) {
        const callId = markLegitimateCall();
        try {
            return await originalCheckAuth.apply(this, args as []);
        } finally {
            // The call ID will be cleaned up by the timeout
        }
    };

    const originalFetch = window.fetch;
    window.fetch = function (...args) {
        const url = args[0];
        if (typeof url === 'string' && url.includes('/v1/whoami')) {
            // Check if this is a legitimate call from AuthOrchestrator
            const requestInit = args[1] || {};
            const callId = (requestInit as any)._legitimateWhoamiCallId;
            if (!callId || !legitimateWhoamiCalls.has(callId)) {
                // This is a direct call to /v1/whoami outside of AuthOrchestrator!
                console.error('🚨 DIRECT /v1/whoami CALL DETECTED! 🚨');
                console.error('This violates the AuthOrchestrator contract.');
                console.error('All /v1/whoami calls must go through AuthOrchestrator.');
                console.error('Use getAuthOrchestrator().checkAuth() instead.');
                console.error('Stack trace:', new Error().stack);

                // In development, throw an error to catch this immediately
                throw new Error('Direct whoami call detected! Use AuthOrchestrator instead.');
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
