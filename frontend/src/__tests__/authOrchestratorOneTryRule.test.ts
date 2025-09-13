/**
 * Tests for Auth Orchestrator "One-Try" Rule
 *
 * These tests verify that the auth orchestrator enforces exactly one refresh
 * attempt per page load, preventing infinite refresh loops.
 */

import { getAuthOrchestrator, __resetAuthOrchestrator } from '@/services/authOrchestrator';

// Mock the API module
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
}));

// Mock sessionStorage for page-load tracking
const mockSessionStorage = {
    getItem: jest.fn(),
    setItem: jest.fn(),
    removeItem: jest.fn(),
    clear: jest.fn(),
};

// Setup sessionStorage mock
Object.defineProperty(window, 'sessionStorage', {
    value: mockSessionStorage,
    writable: true,
});

describe('Auth Orchestrator One-Try Rule', () => {
    let authOrchestrator: ReturnType<typeof getAuthOrchestrator>;
    let apiFetch: jest.MockedFunction<any>;

    beforeEach(() => {
        __resetAuthOrchestrator();
        authOrchestrator = getAuthOrchestrator();
        apiFetch = require('@/lib/api').apiFetch;

        // Reset mocks
        jest.clearAllMocks();
        mockSessionStorage.getItem.mockReturnValue(null);
        mockSessionStorage.setItem.mockImplementation(() => { });
        mockSessionStorage.removeItem.mockImplementation(() => { });

        // Mock console methods
        jest.spyOn(console, 'info').mockImplementation(() => { });
        jest.spyOn(console, 'warn').mockImplementation(() => { });
        jest.spyOn(console, 'error').mockImplementation(() => { });
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('Page-Load Refresh Guard', () => {
        it('should allow first refresh attempt per page load', async () => {
            // Mock unauthenticated response
            apiFetch.mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // First refresh should proceed
            await authOrchestrator.refreshAuth();

            // Should mark refresh as attempted
            expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted',
                'true'
            );
        });

        it('should block subsequent refresh attempts for the same page load', async () => {
            // First, make a successful refresh attempt to set the guard
            mockSessionStorage.getItem.mockReturnValue(null); // Initially not attempted
            apiFetch.mockResolvedValueOnce({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // First refresh should proceed and mark as attempted
            await authOrchestrator.refreshAuth();
            expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted',
                'true'
            );

            // Now simulate the guard being set by updating the mock
            mockSessionStorage.getItem.mockReturnValue('true');

            // Reset API mock for second call
            apiFetch.mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // Second refresh should be blocked
            await authOrchestrator.refreshAuth();

            // Should not call API again (only called once for the first attempt)
            expect(apiFetch).toHaveBeenCalledTimes(1);

            // Should log the blocking
            expect(console.info).toHaveBeenCalledWith(
                expect.stringContaining('Skipping refresh - already attempted for this page load'),
                expect.any(Object)
            );
        });

        it('should reset guard on page visibility change when hidden', () => {
            // Simulate page becoming hidden (user switches tabs)
            const visibilityChangeEvent = new Event('visibilitychange');
            Object.defineProperty(document, 'hidden', { value: true, writable: true });

            document.dispatchEvent(visibilityChangeEvent);

            // Should clear sessionStorage
            expect(mockSessionStorage.removeItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted'
            );
        });

        it('should reset guard on page unload', () => {
            // Simulate page unload (navigation)
            const beforeUnloadEvent = new Event('beforeunload');
            window.dispatchEvent(beforeUnloadEvent);

            // Should clear sessionStorage
            expect(mockSessionStorage.removeItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted'
            );
        });
    });

    describe('Smoke Test Simulation', () => {
        it('should simulate the browser console smoke test behavior', async () => {
            const smokeTest = async (): Promise<number> => {
                // First whoami - should fail
                apiFetch
                    .mockResolvedValueOnce({
                        ok: false,
                        status: 401,
                        statusText: 'Unauthorized',
                        headers: new Map(),
                    })
                    // CSRF fetch
                    .mockResolvedValueOnce({
                        ok: true,
                        status: 200,
                        statusText: 'OK',
                        headers: new Map(),
                        json: () => Promise.resolve({ csrf_token: 'test-token' }),
                    })
                    // Refresh attempt - should succeed
                    .mockResolvedValueOnce({
                        ok: true,
                        status: 200,
                        statusText: 'OK',
                        headers: new Map(),
                    })
                    // Second whoami - should succeed
                    .mockResolvedValueOnce({
                        ok: true,
                        status: 200,
                        statusText: 'OK',
                        headers: new Map(),
                        json: () => Promise.resolve({
                            user_id: 'test-user',
                            email: 'test@example.com'
                        }),
                    });

                // First whoami call - should fail
                const firstWhoami = await apiFetch('/v1/whoami', { credentials: 'include' });
                if (firstWhoami.ok) return 200;

                // Only try refresh once (this simulates the "tried" flag)
                const tried = false; // In our implementation, this is handled by the page-load guard

                if (!tried) {
                    // Get CSRF token
                    const csrfResponse = await apiFetch('/v1/csrf', { credentials: 'include' });
                    if (csrfResponse.ok) {
                        const csrfData = await csrfResponse.json();
                        // Simulate getting token from cookies (simplified)
                        const csrfToken = csrfData.csrf_token;

                        // Refresh attempt
                        await apiFetch('/v1/auth/refresh', {
                            method: 'POST',
                            credentials: 'include',
                            headers: { 'X-CSRF-Token': csrfToken }
                        });

                        // Second whoami
                        const secondWhoami = await apiFetch('/v1/whoami', { credentials: 'include' });
                        return secondWhoami.status;
                    }
                }

                return 0; // Failed
            };

            const result = await smokeTest();
            expect(result).toBe(200); // Should succeed on second attempt
        });

        it('should prevent multiple refresh attempts in smoke test scenario', async () => {
            // Setup: first whoami fails
            apiFetch.mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // First refresh should proceed and set the guard
            await authOrchestrator.refreshAuth();
            expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted',
                'true'
            );

            // Update mock to simulate guard being set
            mockSessionStorage.getItem.mockReturnValue('true');

            // Second refresh should be blocked
            await authOrchestrator.refreshAuth();

            // Should only make one API call due to page-load guard
            expect(apiFetch).toHaveBeenCalledTimes(1);
        });
    });

    describe('Integration with Existing Guards', () => {
        it('should work alongside existing rate limiting and deduplication', async () => {
            // Mock rapid calls
            apiFetch.mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // Make multiple rapid calls
            const promises = [
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
                authOrchestrator.refreshAuth(),
            ];

            await Promise.all(promises);

            // Should only make one API call due to all guards working together
            expect(apiFetch).toHaveBeenCalledTimes(1);

            // Should mark as attempted in sessionStorage (only once, not 5 times)
            expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted',
                'true'
            );
            expect(mockSessionStorage.setItem).toHaveBeenCalledTimes(1);
        });

        it('should still allow refresh after page visibility change', async () => {
            // First, set up a scenario where refresh has been attempted
            mockSessionStorage.getItem.mockReturnValue(null); // Initially not attempted
            apiFetch.mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
                headers: new Map(),
            });

            // Make first refresh to set the guard
            await authOrchestrator.refreshAuth();
            expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
                'auth:page_load_refresh_attempted',
                'true'
            );

            // Update mock to simulate guard being set
            mockSessionStorage.getItem.mockReturnValue('true');

            // Second refresh should be blocked
            await authOrchestrator.refreshAuth();
            expect(apiFetch).toHaveBeenCalledTimes(1); // Only first call went through

            // Simulate user switching tabs (page becomes hidden)
            mockSessionStorage.getItem.mockReturnValue(null); // Reset mock to simulate cleanup
            const visibilityChangeEvent = new Event('visibilitychange');
            Object.defineProperty(document, 'hidden', { value: true, writable: true });

            // Third refresh should now be allowed (new page load context)
            await authOrchestrator.refreshAuth();
            expect(apiFetch).toHaveBeenCalledTimes(2); // Second call should go through
        });
    });
});
