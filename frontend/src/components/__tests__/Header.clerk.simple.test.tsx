import React from 'react';
import { render, screen } from '@testing-library/react';
import { useRouter, usePathname } from 'next/navigation';

// Mock Next.js router and pathname
jest.mock('next/navigation', () => ({
    useRouter: jest.fn(),
    usePathname: jest.fn(),
}));

// Mock Clerk components
jest.mock('@clerk/nextjs', () => ({
    SignedIn: ({ children }: { children: React.ReactNode }) => <div data-testid="signed-in">{children}</div>,
    SignInButton: ({ children }: { children: React.ReactNode }) => <div data-testid="sign-in-button">{children}</div>,
    SignUpButton: ({ children }: { children: React.ReactNode }) => <div data-testid="sign-up-button">{children}</div>,
    UserButton: () => <div data-testid="user-button">User Button</div>,
}));

// Mock other dependencies
jest.mock('@/hooks/useAuth', () => ({
    useAuthState: jest.fn(() => ({
        isAuthenticated: false,
        sessionReady: false,
        whoamiOk: false,
        user: null,
    })),
}));

jest.mock('@/lib/api', () => ({
    getToken: jest.fn(() => null),
    clearTokens: jest.fn(),
    getBudget: jest.fn(() => Promise.resolve({ near_cap: false })),
    bumpAuthEpoch: jest.fn(),
    apiFetch: jest.fn(() => Promise.resolve()),
}));

jest.mock('../ClientOnly', () => {
    return function ClientOnly({ children }: { children: React.ReactNode }) {
        return <div data-testid="client-only">{children}</div>;
    };
});

jest.mock('../ThemeToggle', () => {
    return function ThemeToggle() {
        return <div data-testid="theme-toggle">Theme Toggle</div>;
    };
});

describe('Header Component - Clerk Authentication (Simple)', () => {
    const mockRouter = {
        push: jest.fn(),
        replace: jest.fn(),
    };

    beforeEach(() => {
        (useRouter as jest.Mock).mockReturnValue(mockRouter);
        (usePathname as jest.Mock).mockReturnValue('/');
        // Reset environment variable
        delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    test('should render without Clerk when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is not set', () => {
        const Header = require('../Header').default;
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should render with Clerk when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set', () => {
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = 'test-key';

        const Header = require('../Header').default;
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should handle missing Clerk hooks gracefully', () => {
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = 'test-key';

        // Mock require to throw an error
        const originalRequire = global.require;
        global.require = jest.fn(() => {
            throw new Error('Clerk not available');
        });

        const Header = require('../Header').default;
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();

        // Restore original require
        global.require = originalRequire;
    });

    test('should maintain core functionality when Clerk is disabled', () => {
        // Ensure Clerk is disabled
        delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

        const Header = require('../Header').default;
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should handle environment variable changes', () => {
        // Test with Clerk disabled
        delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
        const Header1 = require('../Header').default;
        const { unmount } = render(<Header1 />);
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        unmount();

        // Test with Clerk enabled
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = 'test-key';
        const Header2 = require('../Header').default;
        render(<Header2 />);
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
    });

    test('should render navigation elements', () => {
        const Header = require('../Header').default;
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should handle component initialization', () => {
        const Header = require('../Header').default;
        render(<Header />);

        // Should render without throwing errors
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
    });
});
