import React from 'react';
import { render, screen } from '@testing-library/react';
import { useRouter, usePathname } from 'next/navigation';
import Header from '../Header';

// Mock Next.js router and pathname
jest.mock('next/navigation', () => ({
    useRouter: jest.fn(),
    usePathname: jest.fn(),
}));

// Clerk removed: no mocks needed

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

describe('Header Component - Cookie Authentication', () => {
    const mockRouter = {
        push: jest.fn(),
        replace: jest.fn(),
    };

    beforeEach(() => {
        (useRouter as jest.Mock).mockReturnValue(mockRouter);
        (usePathname as jest.Mock).mockReturnValue('/');
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    test('renders header with cookie auth only', () => {
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should maintain core functionality when Clerk is disabled', () => {
        // Ensure Clerk is disabled
        delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should handle environment variable changes', () => {
        const { unmount } = render(<Header />);
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        unmount();

        render(<Header />);
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
    });

    test('should render navigation elements', () => {
        render(<Header />);

        expect(screen.getByText('Gesahni')).toBeInTheDocument();
        expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
    });

    test('should handle component initialization', () => {
        render(<Header />);

        // Should render without throwing errors
        expect(screen.getByText('Gesahni')).toBeInTheDocument();
    });
});
