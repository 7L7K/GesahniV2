/**
 * Test the whoami interceptor to ensure it only warns on direct calls
 * and allows legitimate AuthOrchestrator calls to pass through
 */

import { getAuthOrchestrator, __resetAuthOrchestrator } from '@/services/authOrchestrator';

// Mock apiFetch to avoid actual network calls
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn()
}));

// Mock the fetch module used by whoamiResilience
jest.mock('@/lib/api/fetch', () => ({
    apiFetch: jest.fn()
}));

describe('Whoami Interceptor', () => {
    let consoleWarnSpy: jest.SpyInstance;
    let mockApiFetch: jest.MockedFunction<any>;
    let originalFetch: typeof global.fetch;

    beforeEach(() => {
        consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();
        mockApiFetch = require('@/lib/api/fetch').apiFetch;
        __resetAuthOrchestrator();

        // Set up the interceptor manually for testing
        originalFetch = global.fetch;
        global.fetch = jest.fn().mockImplementation((...args) => {
            const url = args[0];
            if (typeof url === 'string' && (url.includes('/v1/whoami') || url.includes('/v1/auth/whoami'))) {
                // Check if the call is coming from the AuthOrchestrator
                const stack = new Error().stack || '';
                const isFromAuthOrchestrator = stack.includes('AuthOrchestrator') ||
                    stack.includes('authOrchestrator') ||
                    stack.includes('checkAuth') ||
                    stack.includes('apiFetch');

                if (!isFromAuthOrchestrator) {
                    throw new Error('Direct whoami call detected! Use AuthOrchestrator instead.');
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

        // Verify that apiFetch was called with the correct endpoint
        expect(mockApiFetch).toHaveBeenCalledWith('/v1/auth/whoami', expect.any(Object));
    });

    it('should throw error when direct fetch calls are made to whoami', () => {
        // Make a direct fetch call to trigger the global interceptor
        // This should throw an error in test/development environment
        expect(() => {
            // eslint-disable-next-line no-restricted-syntax
            fetch('/v1/auth/whoami');
        }).toThrow('Direct whoami call detected! Use AuthOrchestrator instead.');
    });

    it('should allow other fetch calls to pass through without warning', () => {
        // Make a apiFetch call to a different endpoint
        const { apiFetch } = require('@/lib/api/fetch');
        apiFetch('/v1/state');

        // Verify that no warning was logged
        expect(consoleWarnSpy).not.toHaveBeenCalledWith(
            expect.stringContaining('🚨 DIRECT WHOAMI CALL DETECTED!')
        );
    });
});
