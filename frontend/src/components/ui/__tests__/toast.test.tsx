import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { RateLimitToast, AuthMismatchToast } from '../toast';

describe('RateLimitToast', () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    it('should not render initially', () => {
        render(<RateLimitToast />);
        expect(screen.queryByText(/Too many requests/)).not.toBeInTheDocument();
    });

    it('should show toast when rate-limit event is dispatched', () => {
        render(<RateLimitToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('rate-limit', {
                detail: { retryAfter: 30 }
            }));
        });

        expect(screen.getByText(/Too many requests, try again in 30s/)).toBeInTheDocument();
    });

    it('should countdown the timer', () => {
        render(<RateLimitToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('rate-limit', {
                detail: { retryAfter: 3 }
            }));
        });

        expect(screen.getByText(/Too many requests, try again in 3s/)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(1000);
        });

        expect(screen.getByText(/Too many requests, try again in 2s/)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(1000);
        });

        expect(screen.getByText(/Too many requests, try again in 1s/)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(1000);
        });

        expect(screen.getByText(/Too many requests, try again in 0s/)).toBeInTheDocument();
    });

    it('should hide toast when timer reaches 0', () => {
        render(<RateLimitToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('rate-limit', {
                detail: { retryAfter: 1 }
            }));
        });

        expect(screen.getByText(/Too many requests, try again in 1s/)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(1000);
        });

        expect(screen.getByText(/Too many requests, try again in 0s/)).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(1000);
        });

        // The toast should hide after the timer reaches 0
        act(() => {
            jest.advanceTimersByTime(1000);
        });

        expect(screen.queryByText(/Too many requests/)).not.toBeInTheDocument();
    });

    it('should handle missing retryAfter gracefully', () => {
        render(<RateLimitToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('rate-limit', {
                detail: {}
            }));
        });

        expect(screen.getByText(/Too many requests, try again in 0s/)).toBeInTheDocument();
    });
});

describe('AuthMismatchToast', () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    it('should not render initially', () => {
        render(<AuthMismatchToast />);
        expect(screen.queryByText(/Auth mismatch/)).not.toBeInTheDocument();
    });

    it('should show toast when auth-mismatch event is dispatched', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'Auth mismatch—re-login.' }
            }));
        });

        expect(screen.getByText('Auth mismatch—re-login.')).toBeInTheDocument();
    });

    it('should use default message when no message provided', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: {}
            }));
        });

        expect(screen.getByText('Auth mismatch—re-login.')).toBeInTheDocument();
    });

    it('should auto-hide after 5 seconds', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'Custom auth error message' }
            }));
        });

        expect(screen.getByText('Custom auth error message')).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(5000);
        });

        expect(screen.queryByText('Custom auth error message')).not.toBeInTheDocument();
    });

    it('should not hide before 5 seconds', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'Test message' }
            }));
        });

        expect(screen.getByText('Test message')).toBeInTheDocument();

        act(() => {
            jest.advanceTimersByTime(4000);
        });

        expect(screen.getByText('Test message')).toBeInTheDocument();
    });

    it('should handle multiple events correctly', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'First message' }
            }));
        });

        expect(screen.getByText('First message')).toBeInTheDocument();

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'Second message' }
            }));
        });

        expect(screen.getByText('Second message')).toBeInTheDocument();
        expect(screen.queryByText('First message')).not.toBeInTheDocument();
    });

    it('should have correct styling', () => {
        render(<AuthMismatchToast />);

        act(() => {
            window.dispatchEvent(new CustomEvent('auth-mismatch', {
                detail: { message: 'Test message' }
            }));
        });

        const toast = screen.getByText('Test message');
        expect(toast).toHaveStyle({
            position: 'fixed',
            right: '16px',
            bottom: '80px',
            zIndex: '9999',
            background: '#dc2626',
            color: '#fff',
            padding: '12px 14px',
            borderRadius: '12px',
            maxWidth: '300px'
        });
    });
});
