/**
 * Tests for ResilientWhoamiClient
 */

import { ResilientWhoamiClient } from '../whoamiResilience';

describe('ResilientWhoamiClient', () => {
    let client: ResilientWhoamiClient;
    let mockApiFetch: jest.MockedFunction<any>;

    beforeEach(() => {
        client = new ResilientWhoamiClient();
        mockApiFetch = jest.fn();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
        client.clearCache();
    });

    describe('getIdentity', () => {
        it('should return cached identity if fresh', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user',
                email: 'test@example.com'
            };

            mockApiFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockData)
            });

            // First call should fetch from API
            const result1 = await client.getIdentity(mockApiFetch);
            expect(result1).toEqual(mockData);
            expect(mockApiFetch).toHaveBeenCalledTimes(1);

            // Second call within 3 seconds should return cached result
            const result2 = await client.getIdentity(mockApiFetch);
            expect(result2).toEqual(mockData);
            expect(mockApiFetch).toHaveBeenCalledTimes(1); // Still only called once
        });

        it('should retry on network errors', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            // First two calls fail, third succeeds
            mockApiFetch
                .mockRejectedValueOnce(new Error('Network error'))
                .mockRejectedValueOnce(new Error('Timeout'))
                .mockResolvedValueOnce({
                    ok: true,
                    json: () => Promise.resolve(mockData)
                });

            const promise = client.getIdentity(mockApiFetch);

            // Advance timers to process retries
            await jest.advanceTimersByTimeAsync(1000);
            await jest.advanceTimersByTimeAsync(2000);
            await jest.advanceTimersByTimeAsync(4000);

            const result = await promise;
            expect(result).toEqual(mockData);
            expect(mockApiFetch).toHaveBeenCalledTimes(3);
        }, 10000);

        it('should not retry on auth errors', async () => {
            mockApiFetch.mockResolvedValue({
                ok: false,
                status: 401
            });

            // Mock console.warn to avoid noise
            const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

            await expect(client.getIdentity(mockApiFetch)).rejects.toThrow();
            expect(mockApiFetch).toHaveBeenCalledTimes(1); // No retries for 401

            consoleWarnSpy.mockRestore();
        });

        it('should handle max retries exceeded', async () => {
            mockApiFetch.mockRejectedValue(new Error('Network error'));

            // Mock console.warn to avoid noise
            const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

            const promise = client.getIdentity(mockApiFetch);

            // Fast-forward through all retries
            for (let i = 0; i < 3; i++) {
                await jest.advanceTimersByTimeAsync(5000);
            }

            await expect(promise).rejects.toThrow();
            expect(mockApiFetch).toHaveBeenCalledTimes(3);

            consoleWarnSpy.mockRestore();
        }, 30000);
    });

    describe('cache management', () => {
        it('should clear cache when requested', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            mockApiFetch.mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(mockData)
            });

            // First call
            await client.getIdentity(mockApiFetch);
            expect(mockApiFetch).toHaveBeenCalledTimes(1);

            // Second call should use cache
            await client.getIdentity(mockApiFetch);
            expect(mockApiFetch).toHaveBeenCalledTimes(1);

            // Clear cache
            client.clearCache();

            // Third call should fetch again
            await client.getIdentity(mockApiFetch);
            expect(mockApiFetch).toHaveBeenCalledTimes(2);
        });

        it('should expire cache after TTL', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            mockApiFetch.mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(mockData)
            });

            // First call
            await client.getIdentity(mockApiFetch);
            expect(mockApiFetch).toHaveBeenCalledTimes(1);

            // Advance time past TTL
            jest.advanceTimersByTime(4000);

            // Second call should fetch again
            await client.getIdentity(mockApiFetch);
            expect(mockApiFetch).toHaveBeenCalledTimes(2);
        });
    });

    describe('getCacheStatus', () => {
        it('should return correct cache status', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            mockApiFetch.mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(mockData)
            });

            // No cache initially
            expect(client.getCacheStatus()).toEqual({
                hasCache: false,
                cacheAge: 0,
                cacheTtl: 3000,
                isExpired: true
            });

            // After successful call
            await client.getIdentity(mockApiFetch);
            const status = client.getCacheStatus();
            expect(status.hasCache).toBe(true);
            expect(status.cacheAge).toBeGreaterThanOrEqual(0);
            expect(status.cacheTtl).toBe(3000);
            expect(status.isExpired).toBe(false);
        });
    });
});
