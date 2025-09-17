import { renderHook, act } from '@testing-library/react';
import { useMusicDevices } from '../useSpotify';

// Mock the dependencies
jest.mock('@/lib/api', () => ({
    listDevices: jest.fn(),
    fetchSpotifyStatus: jest.fn(),
}));

// Mock the entire authOrchestrator module
jest.mock('@/services/authOrchestrator', () => {
    const mockOrchestrator = {
        getState: jest.fn(),
        subscribe: jest.fn(),
        checkAuth: jest.fn(),
        refreshAuth: jest.fn(),
        getCachedIdentity: jest.fn(),
        markExplicitStateChange: jest.fn(),
        handle401Response: jest.fn(),
        handleRefreshWithRetry: jest.fn(),
        initialize: jest.fn(),
        cleanup: jest.fn(),
    };

    return {
        getAuthOrchestrator: jest.fn(() => mockOrchestrator),
        AuthOrchestratorImpl: jest.fn(() => mockOrchestrator),
    };
});

import { listDevices, fetchSpotifyStatus } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

const mockListDevices = listDevices as jest.MockedFunction<typeof listDevices>;
const mockFetchSpotifyStatus = fetchSpotifyStatus as jest.MockedFunction<typeof fetchSpotifyStatus>;
const mockGetAuthOrchestrator = getAuthOrchestrator as jest.MockedFunction<typeof getAuthOrchestrator>;
const mockOrchestrator = mockGetAuthOrchestrator();

describe('useMusicDevices', () => {
    beforeEach(() => {
        jest.clearAllTimers();
        jest.clearAllMocks();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.clearAllTimers();
        jest.clearAllMocks();
    });

    it('continues polling when devices are found (no auth error)', async () => {
        // Mock auth orchestrator to return authenticated and ready state
        mockOrchestrator.getState.mockReturnValue({
            is_authenticated: true,
            session_ready: true,
        });

        // Mock fetchSpotifyStatus to return connected state
        mockFetchSpotifyStatus.mockImplementation(async () => {
            console.log('fetchSpotifyStatus called, returning connected: true');
            return { connected: true };
        });

        // Mock listDevices to return devices
        mockListDevices.mockResolvedValue({ devices: [{ id: 'device1', name: 'Test Device' }] });
        console.log('Mock setup - listDevices:', mockListDevices);

        const { result } = renderHook(() => useMusicDevices(45000));

        // Wait for initial poll
        await act(async () => {
            jest.advanceTimersByTime(1);
        });

        // Should have checked once
        expect(mockListDevices).toHaveBeenCalledTimes(1);
        expect(result.current.devices).toEqual([{ id: 'device1', name: 'Test Device' }]);

        // Advance time to see if polling continues
        await act(async () => {
            jest.advanceTimersByTime(45000);
        });

        // Should have been called again since no auth error occurred
        expect(mockListDevices).toHaveBeenCalledTimes(2);
    });

    it('stops polling when spotify_not_authenticated error occurs', async () => {
        // Mock auth orchestrator to return authenticated and ready state
        mockOrchestrator.getState.mockReturnValue({
            is_authenticated: true,
            session_ready: true,
        });

        // Mock fetchSpotifyStatus to return connected state
        mockFetchSpotifyStatus.mockResolvedValue({ connected: true });

        // Mock listDevices to return spotify_not_authenticated error
        const authError = { error: { code: 'spotify_not_authenticated' } };
        mockListDevices.mockResolvedValue(authError);

        const { result } = renderHook(() => useMusicDevices(45000));

        // Wait for initial poll
        await act(async () => {
            jest.advanceTimersByTime(1);
        });

        // Should have checked once
        expect(mockListDevices).toHaveBeenCalledTimes(1);

        // Devices should be empty due to auth error
        expect(result.current.devices).toEqual([]);
        expect(result.current.hasChecked).toBe(true);

        // Advance time significantly - polling should NOT continue
        await act(async () => {
            jest.advanceTimersByTime(45000 * 3); // 3x the polling interval
        });

        // Should still only have been called once (polling stopped)
        expect(mockListDevices).toHaveBeenCalledTimes(1);
    });

    it('handles network errors and retries', async () => {
        // Mock auth orchestrator to return authenticated and ready state
        mockOrchestrator.getState.mockReturnValue({
            is_authenticated: true,
            session_ready: true,
        });

        // Mock fetchSpotifyStatus to return connected state
        mockFetchSpotifyStatus.mockResolvedValue({ connected: true });

        // Mock listDevices to reject with network error, then succeed
        mockListDevices
            .mockRejectedValueOnce(new Error('Network Error'))
            .mockResolvedValueOnce({ devices: [{ id: 'device1', name: 'Test Device' }] });

        const { result } = renderHook(() => useMusicDevices(45000));

        // Wait for initial poll (should fail)
        await act(async () => {
            jest.advanceTimersByTime(1);
        });

        // Should have checked once and devices should be empty due to error
        expect(mockListDevices).toHaveBeenCalledTimes(1);
        expect(result.current.devices).toEqual([]);
        expect(result.current.hasChecked).toBe(true);

        // Advance time to trigger retry
        await act(async () => {
            jest.advanceTimersByTime(45000);
        });

        // Should have been called again and now succeed
        expect(mockListDevices).toHaveBeenCalledTimes(2);
        expect(result.current.devices).toEqual([{ id: 'device1', name: 'Test Device' }]);
    });

    it('does not poll when auth orchestrator indicates not ready', async () => {
        // Mock auth orchestrator to return NOT authenticated/ready
        mockOrchestrator.getState.mockReturnValue({
            is_authenticated: false,
            session_ready: false,
        });

        // Mock fetchSpotifyStatus to return not connected
        mockFetchSpotifyStatus.mockResolvedValue({ connected: false });

        const { result } = renderHook(() => useMusicDevices(45000));

        // Wait for initial poll attempt
        await act(async () => {
            jest.advanceTimersByTime(1);
        });

        // Should NOT have called listDevices due to auth gate
        expect(mockListDevices).toHaveBeenCalledTimes(0);
        expect(result.current.devices).toEqual([]);
        // hasChecked should be true since we did attempt to check status
        expect(result.current.hasChecked).toBe(true);
    });
});
