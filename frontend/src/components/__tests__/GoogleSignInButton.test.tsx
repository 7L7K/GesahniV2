import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import GoogleSignInButton from '../GoogleSignInButton';
import { initiateGoogleSignIn } from '@/lib/api';

// Mock the API function
jest.mock('@/lib/api', () => ({
    initiateGoogleSignIn: jest.fn(),
}));

// Mock window.location
const mockLocation = {
    href: '',
};
Object.defineProperty(window, 'location', {
    value: mockLocation,
    writable: true,
});

describe('GoogleSignInButton', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        mockLocation.href = '';
    });

    it('renders Google sign-in button with correct text', () => {
        render(<GoogleSignInButton />);

        expect(screen.getByText('Continue with Google')).toBeInTheDocument();
        expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('shows loading state when clicked', async () => {
        (initiateGoogleSignIn as jest.Mock).mockImplementation(() => new Promise(() => { }));

        render(<GoogleSignInButton />);

        const button = screen.getByRole('button');
        fireEvent.click(button);

        await waitFor(() => {
            expect(screen.getByText('Signing in...')).toBeInTheDocument();
        });
    });

    it('calls initiateGoogleSignIn when clicked', async () => {
        (initiateGoogleSignIn as jest.Mock).mockResolvedValue(undefined);

        render(<GoogleSignInButton next="/dashboard" />);

        const button = screen.getByRole('button');
        fireEvent.click(button);

        await waitFor(() => {
            expect(initiateGoogleSignIn).toHaveBeenCalledWith('/dashboard');
        });
    });

    it('handles errors gracefully', async () => {
        const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => { });
        (initiateGoogleSignIn as jest.Mock).mockRejectedValue(new Error('OAuth failed'));

        render(<GoogleSignInButton />);

        const button = screen.getByRole('button');
        fireEvent.click(button);

        await waitFor(() => {
            expect(consoleSpy).toHaveBeenCalledWith('Google sign-in failed:', expect.any(Error));
        });

        // Button should return to normal state after error
        await waitFor(() => {
            expect(screen.getByText('Continue with Google')).toBeInTheDocument();
        });

        consoleSpy.mockRestore();
    });

    it('is disabled when disabled prop is true', () => {
        render(<GoogleSignInButton disabled={true} />);

        const button = screen.getByRole('button');
        expect(button).toBeDisabled();
    });

    it('is disabled when loading', async () => {
        (initiateGoogleSignIn as jest.Mock).mockImplementation(() => new Promise(() => { }));

        render(<GoogleSignInButton />);

        const button = screen.getByRole('button');
        fireEvent.click(button);

        await waitFor(() => {
            expect(button).toBeDisabled();
        });
    });

    it('applies custom className', () => {
        render(<GoogleSignInButton className="custom-class" />);

        const button = screen.getByRole('button');
        expect(button).toHaveClass('custom-class');
    });
});
