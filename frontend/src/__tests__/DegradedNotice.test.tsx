import React from 'react';
import { render, screen, act } from '@testing-library/react';
import DegradedNotice from '@/components/DegradedNotice';

jest.useFakeTimers();

describe('DegradedNotice', () => {
    afterEach(() => {
        jest.clearAllTimers();
        (global.fetch as any).mockReset?.();
    });

    it('shows warning with failing checks from /healthz/deps', async () => {
        (global.fetch as jest.Mock) = jest.fn()
            // ready ok
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }))
            // deps degraded
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'degraded', checks: { backend: 'ok', llama: 'error' } }), { status: 200, headers: { 'content-type': 'application/json' } }));
        await act(async () => { render(<DegradedNotice />); });
        await act(async () => { });
        expect(screen.getByText(/Some services degraded/i)).toBeInTheDocument();
        expect(screen.getByText(/llama/i)).toBeInTheDocument();
    });

    it('hidden when deps status ok', async () => {
        (global.fetch as jest.Mock) = jest.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }))
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', checks: { backend: 'ok' } }), { status: 200, headers: { 'content-type': 'application/json' } }));
        await act(async () => { render(<DegradedNotice />); });
        await act(async () => { });
        expect(screen.queryByText(/Some services degraded/i)).toBeNull();
    });
});


