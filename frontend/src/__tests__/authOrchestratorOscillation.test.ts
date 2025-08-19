/**
 * Tests for Auth Orchestrator Oscillation Prevention
 * 
 * These tests verify that the auth orchestrator properly prevents oscillation
 * loops where whoamiOk state flips between true/false rapidly.
 */

import { getAuthOrchestrator, __resetAuthOrchestrator } from '@/services/authOrchestrator';
import { getBootstrapManager } from '@/services/bootstrapManager';

// Mock the API module
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
}));

describe('Auth Orchestrator Oscillation Prevention', () => {
    let authOrchestrator: ReturnType<typeof getAuthOrchestrator>;
    let bootstrapManager: ReturnType<typeof getBootstrapManager>;
    let apiFetch: jest.MockedFunction<any>;

    beforeEach(() => {
        __resetAuthOrchestrator();
        authOrchestrator = getAuthOrchestrator();
        bootstrapManager = getBootstrapManager();
        apiFetch = require('@/lib/api').apiFetch;

        // Reset bootstrap manager state
        bootstrapManager.setAuthFinishInProgress(false);

        // Mock console methods to reduce noise in tests
        jest.spyOn(console, 'info').mockImplementation(() => { });
        jest.spyOn(console, 'warn').mockImplementation(() => { });
        jest.spyOn(console, 'error').mockImplementation(() => { });
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('Debouncing', () => {
        it('should debounce rapid successive checkAuth calls', async () => {
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

            // Make multiple rapid calls
            const promises = [
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth()
            ];

            await Promise.all(promises);

            // Should only make one API call due to debouncing
            expect(apiFetch).toHaveBeenCalledTimes(1);
        });
    });

    describe('Oscillation Detection', () => {
        it('should detect rapid whoamiOk state changes', async () => {
            const warnSpy = jest.spyOn(console, 'warn');

            // First, establish a successful state
            apiFetch.mockResolvedValueOnce({
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
            await new Promise(resolve => setTimeout(resolve, 100));

            // Now mock alternating responses to simulate oscillation
            apiFetch
                .mockResolvedValueOnce({
                    ok: false,
                    status: 401,
                    statusText: 'Unauthorized',
                    headers: new Map()
                })
                .mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Map(),
                    json: () => Promise.resolve({
                        user_id: 'test-user',
                        email: 'test@example.com'
                    })
                });

            // Make rapid calls to trigger oscillation
            await authOrchestrator.refreshAuth();
            await new Promise(resolve => setTimeout(resolve, 100));
            await authOrchestrator.refreshAuth();

            // Should detect oscillation
            expect(warnSpy).toHaveBeenCalledWith(
                expect.stringContaining('Potential oscillation detected'),
                expect.any(Object)
            );
        });
    });

    describe('Rate Limiting Integration', () => {
        it('should handle rate limiting and prevent oscillation', async () => {
            const warnSpy = jest.spyOn(console, 'warn');

            // Mock rate limiting response
            apiFetch.mockResolvedValue({
                ok: false,
                status: 429,
                statusText: 'Too Many Requests',
                headers: new Map()
            });

            // Make multiple calls
            const promises = [
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth()
            ];

            await Promise.all(promises);

            // Should apply backoff
            expect(warnSpy).toHaveBeenCalledWith(
                expect.stringContaining('Rate limit hit, applying extended backoff')
            );

            // State should reflect the error
            const state = authOrchestrator.getState();
            expect(state.error).toContain('HTTP 429');
            expect(state.whoamiOk).toBe(false);
        });

        it('should reset oscillation counter on successful calls', async () => {
            // Mock alternating success/failure responses
            apiFetch
                .mockResolvedValueOnce({
                    ok: false,
                    status: 500,
                    statusText: 'Internal Server Error',
                    headers: new Map()
                })
                .mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Map(),
                    json: () => Promise.resolve({
                        user_id: 'test-user',
                        email: 'test@example.com'
                    })
                });

            // Make calls to trigger oscillation detection
            await authOrchestrator.refreshAuth();
            await new Promise(resolve => setTimeout(resolve, 100));
            await authOrchestrator.refreshAuth();

            // Should reset oscillation counter on success
            const state = authOrchestrator.getState();
            expect(state.error).toBeNull();
            expect(state.whoamiOk).toBe(true);
        });
    });

    describe('State Stability', () => {
        it('should maintain stable whoamiOk state during rapid calls', async () => {
            // Mock consistent successful response
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

            // Make multiple rapid calls
            const promises = [];
            for (let i = 0; i < 10; i++) {
                promises.push(authOrchestrator.refreshAuth());
            }

            await Promise.all(promises);

            // State should be stable
            const state = authOrchestrator.getState();
            expect(state.whoamiOk).toBe(true);
            expect(state.isAuthenticated).toBe(true);
            expect(state.sessionReady).toBe(true);
            expect(state.error).toBeNull();
        });
    });

    describe('Cleanup', () => {
        it('should properly cleanup pending operations', async () => {
            // Mock a quick response
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

            // Start an auth check
            const promise = authOrchestrator.refreshAuth();

            // Cleanup immediately
            authOrchestrator.cleanup();

            // Should complete without errors
            await promise;

            // State should be reset
            const state = authOrchestrator.getState();
            expect(state.isLoading).toBe(false);
        });
    });
});
