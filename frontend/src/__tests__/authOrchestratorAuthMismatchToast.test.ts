import { getAuthOrchestrator, __resetAuthOrchestrator } from '@/services/authOrchestrator';

// Mock the apiFetch function
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
    getToken: jest.fn(() => 'mock-token'),
}));

// Mock the bootstrap manager
jest.mock('@/services/bootstrapManager', () => ({
    getBootstrapManager: () => ({
        subscribe: jest.fn(),
    }),
}));

describe('Auth Orchestrator Auth Mismatch Toast', () => {
    let authOrchestrator: any;
    let mockDispatchEvent: jest.Mock;

    // Increase timeout for tests that need to wait for retries
    jest.setTimeout(10000);

    beforeEach(() => {
        __resetAuthOrchestrator();
        authOrchestrator = getAuthOrchestrator();
        jest.clearAllMocks();
        jest.useFakeTimers();

        // Mock window.dispatchEvent
        mockDispatchEvent = jest.fn();
        Object.defineProperty(window, 'dispatchEvent', {
            value: mockDispatchEvent,
            writable: true,
            configurable: true,
        });
    });

    afterEach(() => {
        jest.useRealTimers();
        authOrchestrator.cleanup();
    });

    it('should set state to loggedOut when auth mismatch occurs', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but no userId (first call)
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: null, // No userId
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Mock whoami response with isAuthenticated=true but no userId (retry call)
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: null, // Still no userId after retry
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time to trigger the retry (100ms in test environment)
        jest.advanceTimersByTime(150);

        // Run all timers to complete the retry
        jest.runAllTimers();

        // Check the final state
        const state = authOrchestrator.getState();
        expect(state.isAuthenticated).toBe(false);
        expect(state.sessionReady).toBe(false);
        expect(state.user).toBe(null);
        expect(state.source).toBe('missing');
        expect(state.error).toBe('Auth gate: isAuthenticated=true but no userId after retry');
        expect(state.whoamiOk).toBe(false);
    });

    it('should not dispatch auth-mismatch event if retry succeeds', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but no userId (first call)
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: null, // No userId
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Mock whoami response with valid userId (retry call succeeds)
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: 'valid-user-id', // Now has userId
                email: 'user@example.com',
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time to trigger the retry (100ms in test environment)
        jest.advanceTimersByTime(150);

        // Run all timers to complete the retry
        jest.runAllTimers();

        // Check that auth-mismatch event was NOT dispatched
        expect(mockDispatchEvent).not.toHaveBeenCalledWith(
            expect.objectContaining({
                type: 'auth-mismatch'
            })
        );

        // Verify the state is now authenticated
        const state = authOrchestrator.getState();
        expect(state.isAuthenticated).toBe(true);
        expect(state.user?.id).toBe('valid-user-id');
    });

    it('should use 500ms retry delay in production', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but no userId
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: null,
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time by 400ms - should not have triggered retry yet
        jest.advanceTimersByTime(400);

        // Should only have been called once (initial call)
        expect(apiFetch).toHaveBeenCalledTimes(1);

        // Fast-forward time by 100ms more to reach 500ms
        jest.advanceTimersByTime(100);

        // Run all timers to complete the retry
        jest.runAllTimers();

        // Should now have been called twice (initial + retry)
        expect(apiFetch).toHaveBeenCalledTimes(2);
    });

    it('should use 100ms retry delay in test environment', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but no userId
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: null,
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time by 50ms - should not have triggered retry yet
        jest.advanceTimersByTime(50);

        // Should only have been called once (initial call)
        expect(apiFetch).toHaveBeenCalledTimes(1);

        // Fast-forward time by 50ms more to reach 100ms
        jest.advanceTimersByTime(50);

        // Run all timers to complete the retry
        jest.runAllTimers();

        // Should now have been called twice (initial + retry)
        expect(apiFetch).toHaveBeenCalledTimes(2);
    });

});
