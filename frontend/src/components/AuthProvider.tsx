'use client';

// AuthProvider: initialize the client-side Auth Orchestrator early so
// that components reading `useAuthState()` receive the correct state
// during client hydration. This replaces previous Clerk integration.
import { useEffect } from 'react';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

export default function AuthProvider({ children }: { children: React.ReactNode }) {
    // Initialize auth orchestrator asynchronously in useEffect
    useEffect(() => {
        if (typeof window !== 'undefined') {
            try {
                const orchestrator = getAuthOrchestrator();
                // Expose for debugging
                (window as any).__authOrchestrator = orchestrator;
                // Initialize orchestrator asynchronously (idempotent)
                void orchestrator.initialize();
            } catch (e) {
                // eslint-disable-next-line no-console
                console.error('AuthProvider: error during init', e);
            }
        }
    }, []);

    // Cleanup in separate useEffect
    useEffect(() => {
        return () => {
            if (typeof window !== 'undefined') {
                try {
                    const orchestrator = getAuthOrchestrator();
                    orchestrator.cleanup();
                } catch (e) {
                    // eslint-disable-next-line no-console
                    console.error('AuthProvider: error during cleanup', e);
                }
            }
        };
    }, []);

    return <>{children}</>;
}
