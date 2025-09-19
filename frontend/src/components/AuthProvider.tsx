'use client';

// AuthProvider: initialize the client-side Auth Orchestrator early so
// that components reading `useAuthState()` receive the correct state
// during client hydration. This replaces previous Clerk integration.
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
// Import clearAuthState dynamically to avoid SSR initialization issues
// import { clearAuthState } from '@/lib/api/auth';

export default function AuthProvider({ children }: { children: React.ReactNode }) {
    const router = useRouter();

    // Initialize auth orchestrator and BroadcastChannel listener
    useEffect(() => {
        if (typeof window !== 'undefined') {
            try {
                const orchestrator = getAuthOrchestrator();
                // Expose for debugging
                (window as any).__authOrchestrator = orchestrator;
                // Initialize orchestrator asynchronously (idempotent)
                void orchestrator.initialize();

                // Set up BroadcastChannel listener for instant logout fan-out
                console.log('🔄 AUTH: Setting up BroadcastChannel listener for logout fan-out');
                const bc = new BroadcastChannel('auth');

                bc.onmessage = (event) => {
                    if (event.data?.type === 'logout') {
                        console.log('🔄 AUTH: Received logout broadcast, clearing auth state instantly...', {
                            timestamp: event.data.timestamp,
                            receivedAt: Date.now()
                        });

                        // Clear auth state instantly
                        try {
                            // Import and use the unified auth state clearing function
                            import('@/lib/api/auth').then(({ clearAuthState }) => {
                                clearAuthState();
                            }).catch((error) => {
                                console.warn('🔄 AUTH: Could not import clearAuthState:', error);
                            });

                            // Force auth refresh
                            void orchestrator.refreshAuth({ force: true, noDedupe: true, noCache: true });
                            console.log('🔄 AUTH: Auth refresh triggered');

                            // Navigate to login (only if not already there)
                            const currentPath = window.location.pathname;
                            if (!currentPath.includes('/login') && !currentPath.includes('/logout')) {
                                console.log('🔄 AUTH: Navigating to login page');
                                router.push('/login?logout=broadcast');
                            } else {
                                console.log('🔄 AUTH: Already on login/logout page, skipping navigation');
                            }

                            console.log('🔄 AUTH: Instant logout fan-out completed');
                        } catch (error) {
                            console.error('🔄 AUTH: Error during instant logout:', error);
                        }
                    }
                };

                // Store reference for cleanup
                (window as any).__authBroadcastChannel = bc;

            } catch (e) {
                // eslint-disable-next-line no-console
                console.error('AuthProvider: error during init', e);
            }
        }
    }, [router]);

    // Cleanup in separate useEffect
    useEffect(() => {
        return () => {
            if (typeof window !== 'undefined') {
                try {
                    const orchestrator = getAuthOrchestrator();
                    orchestrator.cleanup();

                    // Clean up BroadcastChannel
                    const bc = (window as any).__authBroadcastChannel;
                    if (bc) {
                        console.log('🔄 AUTH: Cleaning up BroadcastChannel listener');
                        bc.close();
                        delete (window as any).__authBroadcastChannel;
                    }
                } catch (e) {
                    // eslint-disable-next-line no-console
                    console.error('AuthProvider: error during cleanup', e);
                }
            }
        };
    }, []);

    return <>{children}</>;
}
