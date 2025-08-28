import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import Page from '../page';

// Mock Next.js router
jest.mock('next/navigation', () => ({
    useRouter: jest.fn(),
}));

// Mock the auth hooks
jest.mock('@/hooks/useAuth', () => ({
    useAuthState: jest.fn(),
    useAuthOrchestrator: jest.fn(),
}));

// Mock the bootstrap hook
jest.mock('@/hooks/useBootstrap', () => ({
    useBootstrapManager: jest.fn(),
}));

// Mock the API functions
jest.mock('@/lib/api', () => ({
    sendPrompt: jest.fn(),
    getToken: jest.fn(),
    getMusicState: jest.fn(),
    apiFetch: jest.fn(),
    isAuthed: jest.fn(),
    handleAuthError: jest.fn(),
}));

// Mock the WebSocket hub
jest.mock('@/services/wsHub', () => ({
    wsHub: {
        start: jest.fn(),
        stop: jest.fn(),
        getConnectionStatus: jest.fn(() => 'connected'),
        subscribe: jest.fn(() => jest.fn()),
    },
}));

// Clerk removed: no mocks needed

// Mock music components
jest.mock('@/components/music/NowPlayingCard', () => ({
    __esModule: true,
    default: ({ state }: { state: any }) => <div data-testid="now-playing">Now Playing</div>,
}));

jest.mock('@/components/music/DiscoveryCard', () => ({
    __esModule: true,
    default: () => <div data-testid="discovery">Discovery</div>,
}));

jest.mock('@/components/music/MoodDial', () => ({
    __esModule: true,
    default: () => <div data-testid="mood-dial">Mood Dial</div>,
}));

jest.mock('@/components/music/QueueCard', () => ({
    __esModule: true,
    default: () => <div data-testid="queue">Queue</div>,
}));

jest.mock('@/components/music/DevicePicker', () => ({
    __esModule: true,
    default: () => <div data-testid="device-picker">Device Picker</div>,
}));

// Mock other components
jest.mock('@/components/ChatBubble', () => ({
    __esModule: true,
    default: ({ text }: { text: string }) => <div data-testid="chat-bubble">{text}</div>,
}));

jest.mock('@/components/LoadingBubble', () => ({
    __esModule: true,
    default: () => <div data-testid="loading-bubble">Loading...</div>,
}));

jest.mock('@/components/InputBar', () => ({
    __esModule: true,
    default: () => <div data-testid="input-bar">Input Bar</div>,
}));

jest.mock('@/components/ui/toast', () => ({
    RateLimitToast: () => <div data-testid="rate-limit-toast">Rate Limit Toast</div>,
}));

jest.mock('@/components/WebSocketStatus', () => ({
    WebSocketStatus: () => <div data-testid="websocket-status">WebSocket Status</div>,
}));

describe('Page Music Authentication', () => {
    const mockRouter = {
        replace: jest.fn(),
        push: jest.fn(),
    };

    const mockAuthState = {
        isAuthenticated: true,
        sessionReady: true,
        user: { id: 'testuser', email: 'test@example.com' },
        source: 'cookie' as const,
        version: 1,
        lastChecked: Date.now(),
        isLoading: false,
        error: null,
        whoamiOk: true,
    };

    const mockAuthOrchestrator = {
        refreshAuth: jest.fn(),
    };

    const mockBootstrapManager = {
        initialize: jest.fn().mockResolvedValue(true),
        subscribe: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
        (useRouter as jest.Mock).mockReturnValue(mockRouter);

        const { useAuthState, useAuthOrchestrator } = require('@/hooks/useAuth');
        useAuthState.mockReturnValue(mockAuthState);
        useAuthOrchestrator.mockReturnValue(mockAuthOrchestrator);

        const { useBootstrapManager } = require('@/hooks/useBootstrap');
        useBootstrapManager.mockReturnValue(mockBootstrapManager);
    });

    it('should handle music state authentication errors gracefully', async () => {
        const { getMusicState, handleAuthError } = require('@/lib/api');

        // Mock music state fetch to fail with authentication error
        getMusicState.mockRejectedValueOnce(new Error('Unauthorized: Invalid token'));
        handleAuthError.mockResolvedValueOnce(undefined);

        render(<Page />);

        // Wait for the music state fetch to be called
        await waitFor(() => {
            expect(getMusicState).toHaveBeenCalled();
        });

        // Verify that auth error handling was triggered
        await waitFor(() => {
            expect(handleAuthError).toHaveBeenCalledWith(
                expect.any(Error),
                'music state fetch'
            );
        });
    });

    it('should retry music state fetch after authentication refresh', async () => {
        const { getMusicState, handleAuthError } = require('@/lib/api');

        // Mock first call to fail, second to succeed
        getMusicState
            .mockRejectedValueOnce(new Error('Unauthorized: Invalid token'))
            .mockResolvedValueOnce({
                vibe: { name: 'Calm Night', energy: 0.25, tempo: 80, explicit: false },
                volume: 25,
                device_id: null,
                progress_ms: null,
                is_playing: null,
                track: null,
                quiet_hours: false,
                explicit_allowed: false,
                provider: 'spotify',
                radio_url: 'https://api-staging.gesahni.com/static/radio.mp3',
                radio_playing: null,
            });

        handleAuthError.mockResolvedValueOnce(undefined);

        render(<Page />);

        // Wait for the retry to happen
        await waitFor(() => {
            expect(getMusicState).toHaveBeenCalledTimes(2);
        }, { timeout: 3000 });
    });

    it('should show authentication error UI when music state fetch fails', async () => {
        const { getMusicState } = require('@/lib/api');

        // Mock music state fetch to fail with authentication error
        getMusicState.mockRejectedValueOnce(new Error('Unauthorized: Invalid token'));

        render(<Page />);

        // Wait for the error to be displayed
        await waitFor(() => {
            expect(screen.getByText('Music Access Required')).toBeInTheDocument();
        });
    });

    it('should clear authentication error when authentication is restored', async () => {
        const { getMusicState } = require('@/lib/api');

        // Mock music state fetch to succeed
        getMusicState.mockResolvedValueOnce({
            vibe: { name: 'Calm Night', energy: 0.25, tempo: 80, explicit: false },
            volume: 25,
            device_id: null,
            progress_ms: null,
            is_playing: null,
            track: null,
            quiet_hours: false,
            explicit_allowed: false,
            provider: 'spotify',
            radio_url: 'https://api-staging.gesahni.com/static/radio.mp3',
            radio_playing: null,
        });

        render(<Page />);

        // Wait for music state to be loaded
        await waitFor(() => {
            expect(screen.queryByText('Music Access Required')).not.toBeInTheDocument();
        });
    });
});
