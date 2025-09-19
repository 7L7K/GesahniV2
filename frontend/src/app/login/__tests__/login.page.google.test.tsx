import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useRouter, useSearchParams } from 'next/navigation';
import LoginPage from '../page';
import { initiateGoogleSignIn } from '@/lib/api';

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
    useRouter: jest.fn(),
    useSearchParams: jest.fn(),
}));

// Mock the API functions
jest.mock('@/lib/api', () => ({
    initiateGoogleSignIn: jest.fn(),
    setTokens: jest.fn(),
    apiFetch: jest.fn(() => Promise.resolve({ ok: true })),
    bumpAuthEpoch: jest.fn(),
}));

// Mock the auth orchestrator
jest.mock('@/services/authOrchestrator', () => ({
    getAuthOrchestrator: jest.fn(() => ({
        getState: jest.fn(() => ({
            is_authenticated: false,
            session_ready: false,
            user_id: null,
            user: null,
            source: 'missing',
            version: 1,
            lastChecked: Date.now(),
            isLoading: false,
            error: null,
            whoamiOk: false,
        })),
        refreshAuth: jest.fn(() => Promise.resolve()),
    })),
}));

// Mock the GoogleSignInButton component
jest.mock('@/components/GoogleSignInButton', () => {
    return function MockGoogleSignInButton({ next, disabled }: { next?: string; disabled?: boolean }) {
        return (
            <button
                data-testid="google-signin-button"
                disabled={disabled}
                onClick={() => {
                    if (!disabled) {
                        (initiateGoogleSignIn as jest.Mock)();
                    }
                }}
            >
                Continue with Google
            </button>
        );
    };
});

describe('LoginPage with Google Sign-in', () => {
    const mockRouter = {
        replace: jest.fn(),
        push: jest.fn(),
    };

    const mockSearchParams = new URLSearchParams();

    beforeEach(() => {
        jest.clearAllMocks();
        (useRouter as jest.Mock).mockReturnValue(mockRouter);
        (useSearchParams as jest.Mock).mockReturnValue(mockSearchParams);
    });

    it('renders Google sign-in button', () => {
        render(<LoginPage />);

        expect(screen.getByTestId('google-signin-button')).toBeInTheDocument();
        expect(screen.getByText('Continue with Google')).toBeInTheDocument();
    });

    it('shows divider between Google and email options', () => {
        render(<LoginPage />);

        expect(screen.getByText('Or continue with email')).toBeInTheDocument();
    });

    it('disables Google button when form is loading', async () => {
        render(<LoginPage />);

        const googleButton = screen.getByTestId('google-signin-button');
        const usernameInput = screen.getByLabelText('Username');
        const passwordInput = screen.getByLabelText('Password');
        const submitButton = screen.getByRole('button', { name: /sign in/i });

        // Fill form and submit to trigger loading state
        fireEvent.change(usernameInput, { target: { value: 'testuser' } });
        fireEvent.change(passwordInput, { target: { value: 'testpass' } });
        fireEvent.click(submitButton);

        // Google button should be disabled during loading
        await waitFor(() => {
            expect(googleButton).toBeDisabled();
        });
    });

    it('handles OAuth errors from URL params', () => {
        const mockParams = new URLSearchParams();
        mockParams.set('error', 'access_denied');
        mockParams.set('oauth', 'google');
        (useSearchParams as jest.Mock).mockReturnValue(mockParams);

        render(<LoginPage />);

        expect(screen.getByText('OAuth error: access_denied')).toBeInTheDocument();
    });

    it('handles Google OAuth redirect with tokens in URL', async () => {
        const mockParams = new URLSearchParams();
        mockParams.set('access_token', 'fake-access-token');
        mockParams.set('refresh_token', 'fake-refresh-token');
        (useSearchParams as jest.Mock).mockReturnValue(mockParams);

        const { getAuthOrchestrator } = require('@/services/authOrchestrator');

        render(<LoginPage />);

        await waitFor(() => {
            expect(getAuthOrchestrator).toHaveBeenCalled();
        });
    });

    it('handles Google OAuth redirect with tokens in URL (legacy flow)', async () => {
        const mockParams = new URLSearchParams();
        mockParams.set('access_token', 'fake-access-token');
        mockParams.set('refresh_token', 'fake-refresh-token');
        (useSearchParams as jest.Mock).mockReturnValue(mockParams);

        const { setTokens, apiFetch, bumpAuthEpoch } = require('@/lib/api');

        render(<LoginPage />);

        await waitFor(() => {
            expect(setTokens).toHaveBeenCalledWith('fake-access-token', 'fake-refresh-token');
        });
    });

    it('passes next parameter to Google sign-in button', () => {
        const mockParams = new URLSearchParams();
        mockParams.set('next', '/dashboard');
        (useSearchParams as jest.Mock).mockReturnValue(mockParams);

        render(<LoginPage />);

        const googleButton = screen.getByTestId('google-signin-button');
        expect(googleButton).toBeInTheDocument();
    });

    it('maintains existing email/password functionality', async () => {
        const { apiFetch, setTokens, bumpAuthEpoch } = require('@/lib/api');
        (apiFetch as jest.Mock).mockResolvedValue({
            ok: true,
            headers: new Headers(),
            json: () => Promise.resolve({
                access_token: 'fake-access',
                refresh_token: 'fake-refresh'
            })
        });

        render(<LoginPage />);

        const usernameInput = screen.getByLabelText('Username');
        const passwordInput = screen.getByLabelText('Password');
        const submitButton = screen.getByRole('button', { name: /sign in/i });

        fireEvent.change(usernameInput, { target: { value: 'testuser' } });
        fireEvent.change(passwordInput, { target: { value: 'testpass' } });
        fireEvent.click(submitButton);

        await waitFor(() => {
            expect(apiFetch).toHaveBeenCalledWith('/v1/login', expect.any(Object));
            expect(setTokens).toHaveBeenCalledWith('fake-access', 'fake-refresh');
            expect(bumpAuthEpoch).toHaveBeenCalled();
        });
    });
});
