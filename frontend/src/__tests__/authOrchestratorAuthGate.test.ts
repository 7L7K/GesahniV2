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

describe('Auth Orchestrator Auth Gate', () => {
    let authOrchestrator: any;

    // Increase timeout for tests that need to wait for retries
    jest.setTimeout(10000);

    beforeEach(() => {
        __resetAuthOrchestrator();
        authOrchestrator = getAuthOrchestrator();
        jest.clearAllMocks();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
        authOrchestrator.cleanup();
    });

    it('should treat isAuthenticated=true && !userId as not authenticated', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but no userId
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

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time to trigger the retry
        jest.advanceTimersByTime(200);

        // Get the current state
        const state = authOrchestrator.getState();

        // Should be treated as not authenticated
        expect(state.isAuthenticated).toBe(false);
        expect(state.user).toBe(null);
        expect(state.whoamiOk).toBe(false);
    });

    it('should accept valid userId with isAuthenticated=true', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with valid authentication
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: 'valid-user-id',
                email: 'user@example.com',
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Get the current state
        const state = authOrchestrator.getState();

        // Should be authenticated
        expect(state.isAuthenticated).toBe(true);
        expect(state.user?.id).toBe('valid-user-id');
        expect(state.user?.email).toBe('user@example.com');
        expect(state.whoamiOk).toBe(true);
        expect(state.error).toBe(null);
    });

    it('should handle isAuthenticated=false regardless of userId', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=false
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: false,
                user_id: 'some-user-id', // Even if userId exists
                email: 'user@example.com',
                session_ready: false,
                source: 'missing'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Get the current state
        const state = authOrchestrator.getState();

        // Should be treated as not authenticated
        expect(state.isAuthenticated).toBe(false);
        expect(state.user).toBe(null);
        expect(state.whoamiOk).toBe(false);
    });

    it('should handle empty string userId as invalid', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but empty userId
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: '', // Empty string
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time to trigger the retry
        jest.advanceTimersByTime(200);

        // Get the current state
        const state = authOrchestrator.getState();

        // Should be treated as not authenticated
        expect(state.isAuthenticated).toBe(false);
        expect(state.user).toBe(null);
        expect(state.whoamiOk).toBe(false);
    });

    it('should handle whitespace-only userId as invalid', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock whoami response with isAuthenticated=true but whitespace-only userId
        apiFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                is_authenticated: true,
                user_id: '   ', // Whitespace only
                email: null,
                session_ready: true,
                source: 'cookie'
            })
        });

        // Initialize the orchestrator
        await authOrchestrator.initialize();

        // Fast-forward time to trigger the retry
        jest.advanceTimersByTime(200);

        // Get the current state
        const state = authOrchestrator.getState();

        // Should be treated as not authenticated
        expect(state.isAuthenticated).toBe(false);
        expect(state.user).toBe(null);
        expect(state.whoamiOk).toBe(false);
    });
});
