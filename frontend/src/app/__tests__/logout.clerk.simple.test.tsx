import React from 'react';
import { render, screen } from '@testing-library/react';
import { useRouter } from 'next/navigation';

// Mock Next.js router
jest.mock('next/navigation', () => ({
    useRouter: jest.fn(),
}));

// Mock API functions
jest.mock('@/lib/api', () => ({
    clearTokens: jest.fn(),
    apiFetch: jest.fn(() => Promise.resolve()),
}));

describe('LogoutPage Component - Cookie Authentication', () => {
    const mockRouter = {
        push: jest.fn(),
        replace: jest.fn(),
    };

    beforeEach(() => {
        (useRouter as jest.Mock).mockReturnValue(mockRouter);
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    test('should render logout message', () => {
        const LogoutPage = require('../logout/page').default;
        render(<LogoutPage />);

        expect(screen.getByText('Signing you out…')).toBeInTheDocument();
    });

    test('should render logout status consistently', () => {
        const LogoutPage = require('../logout/page').default;
        render(<LogoutPage />);
        expect(screen.getByText('Signing you out…')).toBeInTheDocument();
    });

    test('should handle component initialization', () => {
        const LogoutPage = require('../logout/page').default;
        render(<LogoutPage />);

        // Should render without throwing errors
        expect(screen.getByText('Signing you out…')).toBeInTheDocument();
    });
});
