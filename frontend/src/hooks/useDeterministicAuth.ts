import { useState, useCallback } from 'react';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

export type DeterministicAuthStatus = 'checking' | 'authenticated' | 'unauthenticated';

export interface AuthUser {
    id: string | null;
    email: string | null;
}

export interface UseDeterministicAuthReturn {
    status: DeterministicAuthStatus;
    user: AuthUser | null;
    ensureAuth: () => Promise<void>;
}

/**
 * Hook for deterministic auth bootstrap after OAuth redirects
 * This bypasses the normal auth orchestrator for post-OAuth scenarios
 */
export function useDeterministicAuth(): UseDeterministicAuthReturn {
    const [status, setStatus] = useState<DeterministicAuthStatus>('checking');
    const [user, setUser] = useState<AuthUser | null>(null);

    const ensureAuth = useCallback(async () => {
        try {
            setStatus('checking');

            // Always include credentials for cookie-based auth
            console.log('🔐 DETERMINISTIC AUTH: Starting post-OAuth auth bootstrap');

            // Use the centralized AuthOrchestrator to perform whoami/checkAuth.
            // Avoid unconditional POST /v1/refresh here — that causes refresh spam.
            const orchestrator = getAuthOrchestrator();

            // Short-circuit: if orchestrator already indicates a successful whoami, use it
            const current = orchestrator.getState();
            if (current.whoamiOk || (current.is_authenticated && current.user_id)) {
                setUser(current.user ? { id: current.user.id, email: current.user.email } : null);
                setStatus(current.whoamiOk ? 'authenticated' : (current.is_authenticated ? 'authenticated' : 'unauthenticated'));
                // Strip query params once after success
                if (typeof window !== 'undefined' && window.location.search && !sessionStorage.getItem('auth:params_stripped')) {
                    const clean = window.location.pathname + window.location.hash;
                    window.history.replaceState({}, document.title, clean);
                    sessionStorage.setItem('auth:params_stripped', '1');
                }
                return;
            }

            // Trigger a centralized auth check (this performs whoami internally)
            await orchestrator.checkAuth();

            const s = orchestrator.getState();
            if (s.whoamiOk || (s.is_authenticated && s.user_id)) {
                setUser(s.user ? { id: s.user.id, email: s.user.email } : null);
                setStatus('authenticated');

                // Strip query params once after first successful whoami
                if (typeof window !== 'undefined' && window.location.search && !sessionStorage.getItem('auth:params_stripped')) {
                    const clean = window.location.pathname + window.location.hash;
                    window.history.replaceState({}, document.title, clean);
                    sessionStorage.setItem('auth:params_stripped', '1');
                }
                console.log('🔐 DETERMINISTIC AUTH: Authentication bootstrap completed successfully (via orchestrator)');
            } else {
                setUser(null);
                setStatus('unauthenticated');
                console.log('🔐 DETERMINISTIC AUTH: Authentication bootstrap resulted in unauthenticated state');
            }
        } catch (error) {
            console.error('🔐 DETERMINISTIC AUTH: Authentication bootstrap failed:', error);
            setUser(null);
            setStatus('unauthenticated');
        }
    }, []);

    return { status, user, ensureAuth };
}
