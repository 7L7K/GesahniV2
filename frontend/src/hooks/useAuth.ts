'use client';

import { useState, useEffect } from 'react';
import { getAuthOrchestrator, type AuthState, type AuthOrchestrator } from '@/services/authOrchestrator';

/**
 * Hook to access the current authentication state
 * This is the preferred way for React components to read auth state
 */
export function useAuthState(): AuthState {
    const [state, setState] = useState<AuthState>(() => getAuthOrchestrator().getState());

    useEffect(() => {
        const unsubscribe = getAuthOrchestrator().subscribe(setState);
        return unsubscribe;
    }, []);

    return state;
}

/**
 * Hook to access the Auth Orchestrator instance
 * Use this when you need to trigger auth actions
 */
export function useAuthOrchestrator(): AuthOrchestrator {
    return getAuthOrchestrator();
}

/**
 * Convenience hook that returns both state and orchestrator
 */
export function useAuth(): { state: AuthState; orchestrator: AuthOrchestrator } {
    const state = useAuthState();
    const orchestrator = useAuthOrchestrator();

    return { state, orchestrator };
}
