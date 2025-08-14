import React from 'react';
import { render, screen, act } from '@testing-library/react';
import BackendBanner from '@/components/BackendBanner';

jest.useFakeTimers();

describe('BackendBanner', () => {
    afterEach(() => {
        jest.clearAllTimers();
        (global.fetch as any).mockReset?.();
    });

    it('renders while offline and disappears when ready flips online', async () => {
        (global.fetch as jest.Mock) = jest.fn()
            // ready 503 → offline
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'fail' }), { status: 503, headers: { 'content-type': 'application/json' } }))
            // deps ok (ignored by banner)
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', checks: { backend: 'ok' } }), { status: 200, headers: { 'content-type': 'application/json' } }))
            // ready ok on next tick
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }));

        await act(async () => { render(<BackendBanner />); });
        // allow initial effect microtasks
        await act(async () => { });
        expect(screen.getByText(/Backend offline — retrying/i)).toBeInTheDocument();
        // advance 3s for re-poll
        await act(async () => { jest.advanceTimersByTime(3000); });
        await act(async () => { });
        expect(screen.queryByText(/Backend offline — retrying/i)).toBeNull();

        // Validate fetch options for no cookies, no-store
        const init = (global.fetch as jest.Mock).mock.calls[0][1];
        expect(init.credentials).toBe('omit');
        expect(init.cache).toBe('no-store');
    });
});


