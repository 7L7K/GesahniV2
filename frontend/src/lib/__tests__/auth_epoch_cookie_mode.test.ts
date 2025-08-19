/** @jest-environment jsdom */

// Tests for auth epoch bumps and auth-sensitive cache keys

describe('auth epoch + cache keys', () => {
    beforeEach(() => {
        localStorage.clear();
        (global as any).fetch = jest.fn();
    });
    afterEach(() => {
        // @ts-ignore
        (global as any).fetch = undefined;
        jest.restoreAllMocks();
    });

    test('login bumps auth epoch', async () => {
        const { login, getAuthEpoch } = require('@/lib/api') as { login: Function; getAuthEpoch: () => string };
        // First epoch should be '0'
        expect(getAuthEpoch()).toBe('0');
        // Successful login response
        (global as any).fetch = jest.fn(async () => new Response(JSON.stringify({ access_token: 'x' }), { status: 200, headers: { 'content-type': 'application/json' } } as any));
        await login('u', 'p');
        expect(getAuthEpoch()).not.toBe('0');
    });

    test('register bumps auth epoch', async () => {
        const { register, getAuthEpoch } = require('@/lib/api') as { register: Function; getAuthEpoch: () => string };
        expect(getAuthEpoch()).toBe('0');
        (global as any).fetch = jest.fn(async () => new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } } as any));
        await register('u', 'p');
        expect(getAuthEpoch()).not.toBe('0');
    });

    test('epoch segregates short cache across accounts (no stale reuse after login)', async () => {
        const { apiFetch, login } = require('@/lib/api') as { apiFetch: Function; login: Function };
        // 1) First GET caches short response under hdr:anon
        (global as any).fetch = jest
            .fn()
            // First GET => "A"
            .mockResolvedValueOnce(new Response('A', { status: 200 } as any))
            // Login POST => JSON
            .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'x' }), { status: 200, headers: { 'content-type': 'application/json' } } as any))
            // Second GET (after bump) => "B"
            .mockResolvedValueOnce(new Response('B', { status: 200 } as any));

        const r1 = await apiFetch('/v1/profile', { method: 'GET' });
        expect(await r1.text()).toBe('A');
        // 2) Login bumps epoch to a new namespace
        await login('u', 'p');
        // 3) Second GET should not reuse cached 'A' (different key because epoch changed)
        const r2 = await apiFetch('/v1/profile', { method: 'GET' });
        expect(await r2.text()).toBe('B');
    });

    test('device context prevents short-cache reuse across device_id changes', async () => {
        const { getMusicState } = require('@/lib/api') as { getMusicState: () => Promise<{ device_id: string | null }> };
        localStorage.setItem('music:device_id', 'd1');
        (global as any).fetch = jest
            .fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ device_id: 'd1', vibe: { name: 'x', energy: 0, tempo: 0, explicit: false }, volume: 0, quiet_hours: false, explicit_allowed: true }), { status: 200, headers: { 'content-type': 'application/json' } } as any))
            .mockResolvedValueOnce(new Response(JSON.stringify({ device_id: 'd2', vibe: { name: 'x', energy: 0, tempo: 0, explicit: false }, volume: 0, quiet_hours: false, explicit_allowed: true }), { status: 200, headers: { 'content-type': 'application/json' } } as any));
        const s1 = await getMusicState();
        expect(s1.device_id).toBe('d1');
        localStorage.setItem('music:device_id', 'd2');
        const s2 = await getMusicState();
        expect(s2.device_id).toBe('d2');
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(2);
    });

    test('getTvConfig includes resident_id in query', async () => {
        const { getTvConfig } = require('@/lib/api') as { getTvConfig: (residentId: string, token: string) => Promise<any> };
        (global as any).fetch = jest.fn(async (url: string) => {
            expect(url).toMatch(/resident_id=r1/);
            return new Response(JSON.stringify({ status: 'ok', config: { ambient_rotation: 0, rail: 'safe', default_vibe: 'calm' } }), { status: 200, headers: { 'content-type': 'application/json' } } as any);
        });
        await getTvConfig('r1', 't');
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(1);
    });

    test('clearTokens bumps auth epoch again', async () => {
        const { setTokens, clearTokens, getAuthEpoch } = require('@/lib/api') as { setTokens: Function; clearTokens: Function; getAuthEpoch: () => string };
        const before = getAuthEpoch();
        setTokens('a', 'r');
        const afterSet = getAuthEpoch();
        expect(afterSet).not.toBe(before);
        clearTokens();
        const afterClear = getAuthEpoch();
        expect(afterClear).not.toBe(afterSet);
    });

    test('contextKey affects inflight dedupe: same ctx coalesces, different ctx refetches', async () => {
        const { apiFetch } = require('@/lib/api') as { apiFetch: Function };

        let resolveFirst: ((r: Response) => void) | null = null;
        (global as any).fetch = jest
            .fn()
            // First call stays inflight until we resolve
            .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }))
            // Second (different ctx) resolves immediately
            .mockResolvedValueOnce(new Response('ok-ctxB', { status: 200 } as any));

        // Two concurrent calls with same contextKey should dedupe into one fetch
        const p1 = apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxA' });
        const p2 = apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxA' });
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(1);

        // Resolve the first inflight
        resolveFirst && resolveFirst(new Response('ok-ctxA', { status: 200 } as any));
        const r1 = await p1; const r2 = await p2;
        expect(await r1.text()).toBe('ok-ctxA');
        expect(await r2.text()).toBe('ok-ctxA');

        // Now a call with a different contextKey should trigger a new fetch
        const r3 = await apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxB' });
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(2);
        expect(await r3.text()).toBe('ok-ctxB');
    });
});


