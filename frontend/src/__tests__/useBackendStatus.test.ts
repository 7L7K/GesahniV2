import { renderHook, act } from '@testing-library/react';
import { useBackendStatus } from '@/hooks/useBackendStatus';

jest.useFakeTimers();

describe('useBackendStatus', () => {
    afterEach(() => {
        jest.clearAllTimers();
        (global.fetch as any).mockReset?.();
    });

    it('returns online when /healthz/ready → {status:"ok"}', async () => {
        (global.fetch as jest.Mock) = jest.fn()
            // ready
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }))
            // deps
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', checks: { backend: 'ok' } }), { status: 200, headers: { 'content-type': 'application/json' } }));
        const { result } = renderHook(() => useBackendStatus());
        // Flush initial microtasks
        await act(async () => { });
        expect(result.current.ready).toBe('online');
        // Verify fetch options include omit/no-store via call args inspection for first call
        const init = (global.fetch as jest.Mock).mock.calls[0][1];
        expect(init.credentials).toBe('omit');
        expect(init.cache).toBe('no-store');
    });

    it('returns offline on 503 and keeps polling', async () => {
        (global.fetch as jest.Mock) = jest.fn()
            // ready 503
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'fail' }), { status: 503, headers: { 'content-type': 'application/json' } }))
            // deps ok
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', checks: { backend: 'ok' } }), { status: 200, headers: { 'content-type': 'application/json' } }))
            // ready ok on second poll
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }));
        const { result } = renderHook(() => useBackendStatus());
        await act(async () => { });
        expect(result.current.ready).toBe('offline');
        // advance 3s to trigger re-poll
        await act(async () => { jest.advanceTimersByTime(3000); });
        expect(result.current.ready).toBe('online');
    });
});


