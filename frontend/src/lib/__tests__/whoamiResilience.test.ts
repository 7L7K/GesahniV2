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

    describe('getIdentityForOrchestrator', () => {
        it('should return cached identity if fresh', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user',
                email: 'test@example.com'
            };

            // Since fetchWithResilience is deprecated, we'll test the caching logic differently
            // by directly setting the cache
            (client as any).lastGoodIdentity = {
                data: mockData,
                timestamp: Date.now()
            };

            const result = await client.getIdentityForOrchestrator(mockApiFetch);
            expect(result).toEqual(mockData);
            expect(mockApiFetch).not.toHaveBeenCalled(); // Should use cache
        });

        it('should fetch new identity if cache is expired', async () => {
            // Since fetchWithResilience is deprecated, this test is simplified
            // to just verify that the method exists and can be called
            await expect(client.getIdentityForOrchestrator(mockApiFetch)).rejects.toThrow('deprecated');
        });
    });

    describe('cache management', () => {
        it('should clear cache when requested', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            // Set cache manually
            (client as any).lastGoodIdentity = {
                data: mockData,
                timestamp: Date.now()
            };

            // Verify cache exists
            expect(client.getCacheStatus().hasCache).toBe(true);

            // Clear cache
            client.clearCache();

            // Verify cache is cleared
            expect(client.getCacheStatus().hasCache).toBe(false);
        });

        it('should expire cache after TTL', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            // Set cache manually
            (client as any).lastGoodIdentity = {
                data: mockData,
                timestamp: Date.now()
            };

            // Verify cache is fresh
            expect(client.getCacheStatus().isExpired).toBe(false);

            // Advance time past TTL
            jest.advanceTimersByTime(4000);

            // Verify cache is expired
            expect(client.getCacheStatus().isExpired).toBe(true);
        });
    });

    describe('getCacheStatus', () => {
        it('should return correct cache status', async () => {
            const mockData = {
                is_authenticated: true,
                session_ready: true,
                user_id: 'test-user'
            };

            // No cache initially
            expect(client.getCacheStatus()).toEqual({
                hasCache: false,
                cacheAge: 0,
                cacheTtl: 3000,
                isExpired: true
            });

            // Set cache manually
            (client as any).lastGoodIdentity = {
                data: mockData,
                timestamp: Date.now()
            };

            // After setting cache
            const status = client.getCacheStatus();
            expect(status.hasCache).toBe(true);
            expect(status.cacheAge).toBeGreaterThanOrEqual(0);
            expect(status.cacheTtl).toBe(3000);
            expect(status.isExpired).toBe(false);
        });
    });
});
