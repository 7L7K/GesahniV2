'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
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
 * Hook to access the Auth Orchestrator instance with page-key based refresh guard
 * Use this when you need to trigger auth actions
 * The refresh guard resets on navigation to prevent blocking auth on new routes
 */
export function useAuthOrchestrator(): AuthOrchestrator {
    const router = useRouter();
    const pathname = usePathname();

    // Track which page keys have already attempted refresh
    const hasRefreshed = useRef(new Set<string>());

    // Create a unique key for each route that resets the refresh guard on navigation
    const pageKey = useMemo(() => {
        try {
            // Generate a unique key, with fallback for environments without crypto.randomUUID
            const newKey = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : `fallback-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

            console.info('🔑 PAGE_KEY_GENERATED: New page key created for route navigation', {
                pathname,
                pageKey: newKey,
                previousKeysCount: hasRefreshed.current.size,
                timestamp: new Date().toISOString(),
            });
            return newKey;
        } catch (error) {
            // Fallback if crypto fails for any reason
            const fallbackKey = `error-fallback-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            console.warn('🔑 PAGE_KEY_FALLBACK: Using fallback key due to crypto error', {
                pathname,
                pageKey: fallbackKey,
                error: error instanceof Error ? error.message : String(error),
                timestamp: new Date().toISOString(),
            });
            return fallbackKey;
        }
    }, [pathname]);

    // Log hook initialization
    useEffect(() => {
        console.info('🏗️  PAGE_KEY_HOOK_INIT: useAuthOrchestrator hook initialized', {
            initialPathname: pathname,
            initialPageKey: pageKey,
            timestamp: new Date().toISOString(),
        });
    }, []); // Empty dependency array - only runs once on mount

    // Log when component mounts and page key changes
    useEffect(() => {
        console.info('🎯 PAGE_KEY_ACTIVATED: Page key now active for route', {
            pathname,
            pageKey,
            hasRefreshedCount: hasRefreshed.current.size,
            attemptedRoutes: Array.from(hasRefreshed.current),
            timestamp: new Date().toISOString(),
        });

        // Debug log showing current refresh tracking state
        console.debug('📊 REFRESH_TRACKING_STATE: Current page-key refresh tracking', {
            currentPageKey: pageKey,
            currentPathname: pathname,
            totalKeysTracked: hasRefreshed.current.size,
            keysList: Array.from(hasRefreshed.current),
            timestamp: new Date().toISOString(),
        });
    }, [pathname, pageKey]);

    const orchestrator = getAuthOrchestrator();

    // Wrap the refreshAuth method with page-key guard
    const refreshAuthWithGuard = async (opts: { force?: boolean } = {}) => {
        // Safety check - ensure orchestrator exists
        if (!orchestrator) {
            console.error('❌ AUTH_ORCHESTRATOR_MISSING: Orchestrator not available in useAuthOrchestrator');
            throw new Error('Auth orchestrator not available');
        }
        const { force = false } = opts;
        const guardCheckStart = Date.now();

        console.info('🔍 REFRESH_GUARD_CHECK: Evaluating refresh request', {
            pathname,
            pageKey,
            force,
            hasAttemptedForThisPage: hasRefreshed.current.has(pageKey),
            totalAttemptedKeys: hasRefreshed.current.size,
            attemptedKeys: Array.from(hasRefreshed.current),
            timestamp: new Date().toISOString(),
        });

        // Skip if already refreshed for this page (unless forced)
        if (!force && hasRefreshed.current.has(pageKey)) {
            const guardCheckDuration = Date.now() - guardCheckStart;
            console.info('🚫 REFRESH_GUARD_BLOCKED: Skipping refresh - already attempted for this route', {
                pathname,
                pageKey,
                force,
                reason: 'page_already_attempted',
                guardCheckDuration,
                totalAttemptedKeys: hasRefreshed.current.size,
                timestamp: new Date().toISOString(),
            });
            return;
        }

        // Mark this page as having attempted refresh
        hasRefreshed.current.add(pageKey);
        const guardCheckDuration = Date.now() - guardCheckStart;

        console.info('✅ REFRESH_GUARD_ALLOWED: Proceeding with refresh', {
            pathname,
            pageKey,
            force,
            reason: force ? 'force_flag_set' : 'first_attempt_for_page',
            guardCheckDuration,
            totalAttemptedKeys: hasRefreshed.current.size,
            attemptedKeys: Array.from(hasRefreshed.current),
            timestamp: new Date().toISOString(),
        });

        // Call the actual refresh
        console.info('🚀 REFRESH_EXECUTING: Calling orchestrator.refreshAuth()', {
            pathname,
            pageKey,
            opts,
            timestamp: new Date().toISOString(),
        });

        try {
            const result = await orchestrator.refreshAuth(opts);
            console.info('✅ REFRESH_COMPLETED: Auth refresh finished successfully', {
                pathname,
                pageKey,
                duration: Date.now() - guardCheckStart,
                timestamp: new Date().toISOString(),
            });
            return result;
        } catch (error) {
            console.error('❌ REFRESH_FAILED: Auth refresh threw error', {
                pathname,
                pageKey,
                error: error instanceof Error ? error.message : String(error),
                duration: Date.now() - guardCheckStart,
                timestamp: new Date().toISOString(),
            });
            throw error;
        }
    };

    // Override the refreshAuth method with our page-key guarded version
    try {
        const wrappedOrchestrator = Object.create(orchestrator);
        wrappedOrchestrator.refreshAuth = refreshAuthWithGuard;
        return wrappedOrchestrator;
    } catch (error) {
        console.error('❌ AUTH_ORCHESTRATOR_WRAP_FAILED: Failed to wrap orchestrator', {
            error: error instanceof Error ? error.message : String(error),
            pathname,
            pageKey,
            timestamp: new Date().toISOString(),
        });
        // Fallback to original orchestrator if wrapping fails
        return orchestrator;
    }
}

/**
 * Convenience hook that returns both state and orchestrator
 */
export function useAuth(): { state: AuthState; orchestrator: AuthOrchestrator } {
    const state = useAuthState();
    const orchestrator = useAuthOrchestrator();

    return { state, orchestrator };
}
