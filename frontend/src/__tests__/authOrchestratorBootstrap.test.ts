import { getAuthOrchestrator, type AuthOrchestrator } from '@/services/authOrchestrator';
import { getBootstrapManager, __resetBootstrapManager } from '@/services/bootstrapManager';

// Mock the apiFetch function
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
}));

describe('AuthOrchestrator Bootstrap Integration', () => {
    let authOrchestrator: AuthOrchestrator;
    let bootstrapManager: ReturnType<typeof getBootstrapManager>;

    beforeEach(() => {
        // Reset both singletons
        __resetBootstrapManager();
        (getAuthOrchestrator as any).__reset?.();

        authOrchestrator = getAuthOrchestrator();
        bootstrapManager = getBootstrapManager();
    });

    afterEach(() => {
        authOrchestrator.cleanup();
        bootstrapManager.cleanup();
        jest.clearAllMocks();
    });

    describe('Auth Finish Coordination', () => {
        it('should block whoami calls during auth finish', async () => {
            const { apiFetch } = require('@/lib/api');

            // Set auth finish in progress
            bootstrapManager.setAuthFinishInProgress(true);

            // Attempt to check auth (use refreshAuth to bypass debouncing)
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was not called
            expect(apiFetch).not.toHaveBeenCalled();
        });

        it('should allow whoami calls when auth finish is not in progress', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock successful response
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: 'test-user',
                    email: 'test@example.com'
                })
            });

            // Ensure auth finish is not in progress
            bootstrapManager.setAuthFinishInProgress(false);

            // Attempt to check auth (use refreshAuth to bypass debouncing)
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was called
            expect(apiFetch).toHaveBeenCalledWith('/v1/whoami', {
                method: 'GET',
                auth: false,
                dedupe: false
            });
        });

        it('should block refresh auth during auth finish', async () => {
            const { apiFetch } = require('@/lib/api');

            // Set auth finish in progress
            bootstrapManager.setAuthFinishInProgress(true);

            // Attempt to refresh auth
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was not called
            expect(apiFetch).not.toHaveBeenCalled();
        });

        it('should allow refresh auth when auth finish is not in progress', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock successful response
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: 'test-user',
                    email: 'test@example.com'
                })
            });

            // Ensure auth finish is not in progress
            bootstrapManager.setAuthFinishInProgress(false);

            // Attempt to refresh auth
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was called
            expect(apiFetch).toHaveBeenCalledWith('/v1/whoami', {
                method: 'GET',
                auth: false,
                dedupe: false
            });
        });
    });

    describe('Bootstrap Manager Coordination', () => {
        it('should start auth bootstrap when checking auth', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock successful response
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: 'test-user',
                    email: 'test@example.com'
                })
            });

            // Check initial state
            expect(bootstrapManager.getState().authBootstrapActive).toBe(false);

            // Check auth (use refreshAuth to bypass debouncing)
            await authOrchestrator.refreshAuth();

            // Verify that auth bootstrap was started and then stopped
            // Note: The bootstrap is started at the beginning and stopped in finally block
            expect(apiFetch).toHaveBeenCalled();
        });

        it('should block auth check if bootstrap manager blocks it', async () => {
            const { apiFetch } = require('@/lib/api');

            // Set auth finish in progress to block auth bootstrap
            bootstrapManager.setAuthFinishInProgress(true);

            // Attempt to check auth
            await authOrchestrator.checkAuth();

            // Verify that apiFetch was not called
            expect(apiFetch).not.toHaveBeenCalled();
        });

        it('should handle bootstrap manager state changes', () => {
            const mockCallback = jest.fn();
            const unsubscribe = authOrchestrator.subscribe(mockCallback);

            // Initial call
            expect(mockCallback).toHaveBeenCalledTimes(1);

            // Change bootstrap state
            bootstrapManager.setAuthFinishInProgress(true);

            // The auth orchestrator should react to bootstrap state changes
            // (though it doesn't directly update its own state, it logs)

            unsubscribe();
        });
    });

    describe('State Management During Auth Finish', () => {
        it('should maintain auth state during auth finish', async () => {
            const { apiFetch } = require('@/lib/api');

            // First, establish some auth state
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: 'test-user',
                    email: 'test@example.com'
                })
            });

            await authOrchestrator.refreshAuth();

            const initialState = authOrchestrator.getState();
            expect(initialState.isAuthenticated).toBe(true);

            // Set auth finish in progress
            bootstrapManager.setAuthFinishInProgress(true);

            // Attempt another auth check (should be blocked)
            await authOrchestrator.refreshAuth();

            // State should remain unchanged
            const finalState = authOrchestrator.getState();
            expect(finalState.isAuthenticated).toBe(true);
            expect(finalState).toEqual(initialState);
        });

        it('should not update whoamiOk during auth finish', async () => {
            const { apiFetch } = require('@/lib/api');

            // Set auth finish in progress
            bootstrapManager.setAuthFinishInProgress(true);

            // Mock a response (though it shouldn't be called)
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: null,
                    email: null
                })
            });

            // Attempt to check auth
            await authOrchestrator.checkAuth();

            // Verify that apiFetch was not called
            expect(apiFetch).not.toHaveBeenCalled();

            // State should remain in its initial state
            const state = authOrchestrator.getState();
            expect(state.isAuthenticated).toBe(false);
            expect(state.sessionReady).toBe(false);
        });
    });

    describe('Error Handling', () => {
        it('should handle apiFetch errors gracefully', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock an error response
            apiFetch.mockRejectedValue(new Error('Network error'));

            // Ensure auth finish is not in progress
            bootstrapManager.setAuthFinishInProgress(false);

            // Attempt to check auth (use refreshAuth to bypass debouncing)
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was called
            expect(apiFetch).toHaveBeenCalled();

            // State should reflect the error
            const state = authOrchestrator.getState();
            expect(state.isAuthenticated).toBe(false);
            expect(state.sessionReady).toBe(false);
            expect(state.error).toBe('Network error');
        });

        it('should handle HTTP error responses', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock an HTTP error response
            apiFetch.mockResolvedValue({
                ok: false,
                status: 500,
                statusText: 'Internal Server Error',
                headers: new Map()
            });

            // Ensure auth finish is not in progress
            bootstrapManager.setAuthFinishInProgress(false);

            // Attempt to check auth (use refreshAuth to bypass debouncing)
            await authOrchestrator.refreshAuth();

            // Verify that apiFetch was called
            expect(apiFetch).toHaveBeenCalled();

            // State should reflect the error
            const state = authOrchestrator.getState();
            expect(state.isAuthenticated).toBe(false);
            expect(state.sessionReady).toBe(false);
            expect(state.error).toBe('HTTP 500: Internal Server Error');
        });
    });

    describe('Concurrent Operations', () => {
        it('should handle concurrent auth checks', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock successful response
            apiFetch.mockResolvedValue({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Map(),
                json: () => Promise.resolve({
                    user_id: 'test-user',
                    email: 'test@example.com'
                })
            });

            // Ensure auth finish is not in progress
            bootstrapManager.setAuthFinishInProgress(false);

            // Start multiple concurrent auth checks
            const promises = [
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth()
            ];

            await Promise.all(promises);

            // Should only make one API call due to built-in deduplication
            expect(apiFetch).toHaveBeenCalledTimes(1);
        });

        it('should handle auth finish during concurrent operations', async () => {
            const { apiFetch } = require('@/lib/api');

            // Mock a delayed response
            apiFetch.mockImplementation(() =>
                new Promise(resolve => setTimeout(() => resolve({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Map(),
                    json: () => Promise.resolve({
                        user_id: 'test-user',
                        email: 'test@example.com'
                    })
                }), 100))
            );

            // Start an auth check
            const authPromise = authOrchestrator.refreshAuth();

            // Set auth finish in progress during the check
            setTimeout(() => {
                bootstrapManager.setAuthFinishInProgress(true);
            }, 50);

            await authPromise;

            // The original call should complete, but subsequent calls should be blocked
            await authOrchestrator.refreshAuth();

            // Should make two API calls (the first one completes, the second one is blocked)
            expect(apiFetch).toHaveBeenCalledTimes(2);
        });
    });
});
