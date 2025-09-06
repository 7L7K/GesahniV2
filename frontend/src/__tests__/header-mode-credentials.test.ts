import { apiFetch } from '@/lib/api';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe('Header Mode Credentials Configuration', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        // Clear localStorage
        if (typeof window !== 'undefined') {
            window.localStorage.clear();
        }
        // Set header mode for these tests
        process.env.NEXT_PUBLIC_HEADER_AUTH_MODE = '1';
    });

    it('should use credentials: omit by default in header mode for regular endpoints', async () => {
        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request that should use default credentials and disable dedupe
        await apiFetch('/v1/status', { method: 'GET', dedupe: false });

        // Verify the fetch was called with credentials: 'omit'
        expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                credentials: 'omit'
            })
        );
    });

    it('should use credentials: include for OAuth endpoints even in header mode', async () => {
        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ auth_url: 'https://example.com' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request to OAuth endpoint and disable dedupe
        await apiFetch('/v1/google/auth/login_url', { method: 'GET', dedupe: false });

        // Verify the fetch was called with credentials: 'include'
        expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                credentials: 'include'
            })
        );
    });

    it('should use credentials: include for whoami endpoint even in header mode', async () => {
        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ is_authenticated: false }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request to whoami endpoint and disable dedupe
        // eslint-disable-next-line no-restricted-syntax
        await apiFetch('/v1/whoami', { method: 'GET', dedupe: false });

        // Verify the fetch was called with credentials: 'include'
        expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                credentials: 'include'
            })
        );
    });

    it('should not include Authorization header when no token is present', async () => {
        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request without auth and disable dedupe
        await apiFetch('/v1/status', { method: 'GET', auth: false, dedupe: false });

        // Verify no Authorization header was added
        expect(mockFetch).toHaveBeenCalled();
        const fetchCalls = mockFetch.mock.calls;

        // Find the call for /v1/status
        const statusCall = fetchCalls.find(call => call[0].includes('/v1/status'));
        expect(statusCall).toBeDefined();

        const init = statusCall[1];
        expect(init.headers).not.toHaveProperty('Authorization');
    });

    it('should include Authorization header when token is present and auth is true', async () => {
        // Set a token in localStorage
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('auth:access', 'test-token');
        }

        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request with auth
        await apiFetch('/v1/profile', { method: 'GET', auth: true });

        // Verify Authorization header was added
        expect(mockFetch).toHaveBeenCalled();
        const fetchCalls = mockFetch.mock.calls;

        // Find the call for /v1/profile
        const profileCall = fetchCalls.find(call => call[0].includes('/v1/profile'));
        expect(profileCall).toBeDefined();

        const init = profileCall[1];
        expect(init.headers).toHaveProperty('Authorization', 'Bearer test-token');
    });

    it('should allow explicit credentials override', async () => {
        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request with explicit credentials and disable dedupe
        await apiFetch('/v1/google/auth/login_url', {
            method: 'GET',
            credentials: 'include',
            dedupe: false
        });

        // Verify the explicit credentials were used
        expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                credentials: 'include'
            })
        );
    });

    it('should use credentials: include by default in cookie mode', async () => {
        // Set cookie mode for this test
        process.env.NEXT_PUBLIC_HEADER_AUTH_MODE = '0';

        // Mock a successful response
        mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        // Make a request that should use default credentials and disable dedupe
        await apiFetch('/v1/status', { method: 'GET', dedupe: false });

        // Verify the fetch was called with credentials: 'include'
        expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                credentials: 'include'
            })
        );
    });
});
