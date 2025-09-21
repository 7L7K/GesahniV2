/**
 * Tests for AuthHUD component
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import AuthHUD from '../AuthHUD';
import { useAuthState } from '@/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

// Mock dependencies
jest.mock('@/hooks/useAuth');
jest.mock('@/lib/api');
jest.mock('@/services/authOrchestrator');

const mockUseAuthState = useAuthState as jest.MockedFunction<typeof useAuthState>;
const mockApiFetch = apiFetch as jest.MockedFunction<typeof apiFetch>;
const mockGetAuthOrchestrator = getAuthOrchestrator as jest.MockedFunction<typeof getAuthOrchestrator>;

describe('AuthHUD Component', () => {
    let mockAuthOrchestrator: any;
    let mockAuthState: any;

    beforeEach(() => {
        // Reset mocks
        jest.clearAllMocks();

        // Mock auth orchestrator
        mockAuthOrchestrator = {
            getCachedIdentity: jest.fn().mockReturnValue(null),
            getState: jest.fn(),
            subscribe: jest.fn(),
        };
        mockGetAuthOrchestrator.mockReturnValue(mockAuthOrchestrator);

        // Mock auth state
        mockAuthState = {
            is_authenticated: false,
            session_ready: false,
            user_id: null,
            source: 'missing',
            whoamiOk: false,
            version: 1,
        };
        mockUseAuthState.mockReturnValue(mockAuthState);

        // Mock API responses
        const mockResponse = {
            headers: {
                get: jest.fn().mockReturnValue('test-value'),
            },
            json: jest.fn().mockResolvedValue({}),
        };

        mockApiFetch.mockResolvedValue(mockResponse);
        mockResponse.headers.get.mockImplementation((header) => {
            const mockHeaders: Record<string, string> = {
                'x-req-id': 'test-req-id',
                'x-authdiag-req': 'cookies=["test"]; authz=False; csrf=False',
                'x-authdiag-setcookie': 'csrf_token; HttpOnly=absent',
                'x-authdiag-origin': 'http://localhost:3000',
                'x-authdiag-useragent': 'TestAgent/1.0',
                'x-authdiag-csrf': 'present',
                'x-authdiag-authcookies': 'GSNH_AT,GSNH_RT',
            };
            return mockHeaders[header] || null;
        });
    });

    it('should render with initial auth state', async () => {
        await act(async () => {
            render(<AuthHUD />);
        });

        // Wait for component to load
        await waitFor(() => {
            expect(screen.getByText('Auth HUD')).toBeInTheDocument();
        });

        // Check that basic information is displayed
        expect(screen.getByText('Req-Id:')).toBeInTheDocument();
        expect(screen.getByText('Req:')).toBeInTheDocument();
        expect(screen.getByText('Set-Cookie:')).toBeInTheDocument();
        expect(screen.getByText('Auth State:')).toBeInTheDocument();

        // Check auth state display using more flexible text matching
        expect(screen.getByText(/Authenticated: false/)).toBeInTheDocument();
        expect(screen.getByText(/Session Ready: false/)).toBeInTheDocument();
        expect(screen.getByText(/User ID:/)).toBeInTheDocument();
        expect(screen.getByText(/Source:/)).toBeInTheDocument();
    });

    it('should update auth state when auth state changes', async () => {
        const mockUnsubscribe = jest.fn();

        // Mock subscribe to return the unsubscribe function
        mockAuthOrchestrator.subscribe.mockReturnValue(mockUnsubscribe);

        await act(async () => {
            render(<AuthHUD />);
        });

        // Wait for component to load
        await waitFor(() => {
            expect(screen.getByText('Auth HUD')).toBeInTheDocument();
        });

        // Simulate auth state change
        const newAuthState = {
            ...mockAuthState,
            is_authenticated: true,
            session_ready: true,
            user_id: 'test-user',
            source: 'cookie',
            whoamiOk: true,
            version: 2,
        };

        mockUseAuthState.mockReturnValue(newAuthState);

        // Trigger re-render by changing the mock value
        await act(async () => {
            // This should trigger the useEffect that depends on auth state
        });

        // Verify updated auth state is displayed
        await waitFor(() => {
            expect(screen.getByText(/Authenticated: true/)).toBeInTheDocument();
            expect(screen.getByText(/Session Ready: true/)).toBeInTheDocument();
            expect(screen.getByText('test-user')).toBeInTheDocument();
            expect(screen.getByText(/cookie/)).toBeInTheDocument();
        });
    });

    it('should handle API errors gracefully', async () => {
        // Mock API failure
        mockApiFetch.mockRejectedValue(new Error('Network error'));

        await act(async () => {
            render(<AuthHUD />);
        });

        // Wait for component to load
        await waitFor(() => {
            expect(screen.getByText('Auth HUD')).toBeInTheDocument();
        });

        // Should still display auth state even if diagnostic APIs fail
        expect(screen.getByText(/Authenticated: false/)).toBeInTheDocument();
        expect(screen.getByText(/Session Ready: false/)).toBeInTheDocument();
    });

    it('should cleanup on unmount', async () => {
        const mockUnsubscribe = jest.fn();

        // Mock subscribe to return the unsubscribe function
        mockAuthOrchestrator.subscribe.mockReturnValue(mockUnsubscribe);

        const { unmount } = render(<AuthHUD />);

        unmount();

        // Should have called unsubscribe
        expect(mockUnsubscribe).toHaveBeenCalled();
    });

    it('should display rate limiting information when available', async () => {
        const authStateWithRateLimit = {
            ...mockAuthState,
            rate_limit: {
                active: true,
                status: 'Active',
                endpoint: '/v1/test',
                bucket: 'test-bucket',
                limit: 100,
                remaining: 50,
                used: 50,
                ttl: 60,
                message: 'Rate limit exceeded',
                reset_at: Date.now() + 60000,
                last_updated: Date.now(),
                meta: null,
            },
        };

        mockUseAuthState.mockReturnValue(authStateWithRateLimit);

        await act(async () => {
            render(<AuthHUD />);
        });

        await waitFor(() => {
            expect(screen.getByText(/Rate Limited:/)).toBeInTheDocument();
            expect(screen.getByText(/Rate limit exceeded/)).toBeInTheDocument();
            expect(screen.getByText('/v1/test')).toBeInTheDocument();
            expect(screen.getByText('test-bucket')).toBeInTheDocument();
            expect(screen.getByText('50/100')).toBeInTheDocument();
        });
    });

    it('should show no rate limiting when inactive', async () => {
        await act(async () => {
            render(<AuthHUD />);
        });

        await waitFor(() => {
            expect(screen.getByText(/No active rate limiting/)).toBeInTheDocument();
        });
    });
});
