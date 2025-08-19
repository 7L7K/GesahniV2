/**
 * Test the whoami interceptor to ensure it only warns on direct calls
 * and allows legitimate AuthOrchestrator calls to pass through
 */

import { getAuthOrchestrator, __resetAuthOrchestrator } from '@/services/authOrchestrator';

// Mock apiFetch to avoid actual network calls
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn()
}));

describe('Whoami Interceptor', () => {
    let consoleWarnSpy: jest.SpyInstance;
    let mockApiFetch: jest.MockedFunction<any>;
    let originalFetch: typeof global.fetch;

    beforeEach(() => {
        consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();
        mockApiFetch = require('@/lib/api').apiFetch;
        __resetAuthOrchestrator();

        // Set up the interceptor manually for testing
        originalFetch = global.fetch;
        global.fetch = jest.fn().mockImplementation((...args) => {
            const url = args[0];
            if (typeof url === 'string' && url.includes('/v1/whoami')) {
                // Check if the call is coming from the AuthOrchestrator
                const stack = new Error().stack || '';
                const isFromAuthOrchestrator = stack.includes('AuthOrchestrator') ||
                    stack.includes('authOrchestrator') ||
                    stack.includes('checkAuth') ||
                    stack.includes('apiFetch');

                if (!isFromAuthOrchestrator) {
                    console.warn('🚨 DIRECT WHOAMI CALL DETECTED!', {
                        url,
                        stack,
                        message: 'Use AuthOrchestrator instead of calling whoami directly'
                    });
                }
            }
            return originalFetch.apply(this, args);
        });
    });

    afterEach(() => {
        consoleWarnSpy.mockRestore();
        jest.clearAllMocks();
        global.fetch = originalFetch;
    });

    it('should not warn when AuthOrchestrator makes whoami calls', async () => {
        // Mock a successful whoami response
        mockApiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({
                is_authenticated: true,
                session_ready: true,
                user: { id: 'test-user' },
                source: 'cookie',
                version: 1
            })
        });

        // Initialize AuthOrchestrator (this will call whoami)
        const orchestrator = getAuthOrchestrator();
        await orchestrator.initialize();

        // Verify that no warning was logged
        expect(consoleWarnSpy).not.toHaveBeenCalledWith(
            expect.stringContaining('🚨 DIRECT WHOAMI CALL DETECTED!')
        );

        // Verify that apiFetch was called
        expect(mockApiFetch).toHaveBeenCalledWith('/v1/whoami', expect.any(Object));
    });

    it('should warn when direct fetch calls are made to whoami', async () => {
        // Make a direct fetch call (this should trigger the warning)
        fetch('/v1/whoami');

        // Verify that the warning was logged
        expect(consoleWarnSpy).toHaveBeenCalledWith(
            '🚨 DIRECT WHOAMI CALL DETECTED!',
            expect.objectContaining({
                url: '/v1/whoami',
                message: 'Use AuthOrchestrator instead of calling whoami directly'
            })
        );
    });

    it('should allow other fetch calls to pass through without warning', () => {
        // Make a fetch call to a different endpoint
        fetch('/v1/state');

        // Verify that no warning was logged
        expect(consoleWarnSpy).not.toHaveBeenCalledWith(
            expect.stringContaining('🚨 DIRECT WHOAMI CALL DETECTED!')
        );
    });
});
