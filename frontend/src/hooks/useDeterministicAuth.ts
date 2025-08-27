import { useState, useCallback } from 'react';

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

            // Step 1: Refresh the auth session
            console.log('🔐 DETERMINISTIC AUTH: Calling POST /v1/refresh');
            const refreshResponse = await fetch(`${process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000"}/v1/refresh`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: '{}'
            });

            console.log('🔐 DETERMINISTIC AUTH: Refresh response:', {
                status: refreshResponse.status,
                statusText: refreshResponse.statusText,
                ok: refreshResponse.ok
            });

            // Step 2: Check whoami to get user info
            console.log('🔐 DETERMINISTIC AUTH: Calling GET /v1/whoami');
            const whoamiResponse = await fetch(`${process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000"}/v1/whoami`, {
                credentials: 'include'
            });

            console.log('🔐 DETERMINISTIC AUTH: Whoami response:', {
                status: whoamiResponse.status,
                statusText: whoamiResponse.statusText,
                ok: whoamiResponse.ok
            });

            if (whoamiResponse.ok) {
                const userData = await whoamiResponse.json();
                console.log('🔐 DETERMINISTIC AUTH: Whoami success:', {
                    userId: userData.user_id,
                    email: userData.email,
                    isAuthenticated: userData.is_authenticated
                });

                // Set user in store
                setUser({
                    id: userData.user_id || null,
                    email: userData.email || null
                });

                setStatus('authenticated');
                console.log('🔐 DETERMINISTIC AUTH: Authentication bootstrap completed successfully');
            } else {
                console.log('🔐 DETERMINISTIC AUTH: Whoami failed, user not authenticated');
                setUser(null);
                setStatus('unauthenticated');
            }
        } catch (error) {
            console.error('🔐 DETERMINISTIC AUTH: Authentication bootstrap failed:', error);
            setUser(null);
            setStatus('unauthenticated');
        }
    }, []);

    return { status, user, ensureAuth };
}
