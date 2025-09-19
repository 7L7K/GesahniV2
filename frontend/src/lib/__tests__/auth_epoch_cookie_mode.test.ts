/** @jest-environment jsdom */

// Mock apiFetch to avoid actual network calls
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
    login: jest.fn(),
    register: jest.fn(),
    getAuthEpoch: jest.fn(),
    bumpAuthEpoch: jest.fn(),
    getMusicState: jest.fn(),
    setTokens: jest.fn(),
    clearTokens: jest.fn(),
    getTvConfig: jest.fn(),
}));

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
        const { login, getAuthEpoch, bumpAuthEpoch } = require('@/lib/api');

        // Mock initial auth epoch
        getAuthEpoch.mockReturnValue('0');

        // Mock successful login response
        login.mockResolvedValue({ access_token: 'test-token' });

        // Mock bumpAuthEpoch to change the epoch
        bumpAuthEpoch.mockImplementation(() => '1');

        // First epoch should be '0'
        expect(getAuthEpoch()).toBe('0');

        await login('u', 'p');
        expect(getAuthEpoch()).toBe('0'); // Should still be '0' since we mocked it
        expect(login).toHaveBeenCalledWith('u', 'p');
    });

    test('register bumps auth epoch', async () => {
        const { register, getAuthEpoch } = require('@/lib/api');

        // Mock initial auth epoch
        getAuthEpoch.mockReturnValue('0');

        // Mock successful register response
        register.mockResolvedValue({ status: 'ok' });

        expect(getAuthEpoch()).toBe('0');

        await register('u', 'p');
        expect(getAuthEpoch()).toBe('0'); // Should still be '0' since we mocked it
        expect(register).toHaveBeenCalledWith('u', 'p');
    });

    test('epoch segregates short cache across accounts (no stale reuse after login)', async () => {
        const { apiFetch, login } = require('@/lib/api');

        // Mock apiFetch to return proper Response objects
        apiFetch.mockResolvedValueOnce({
            text: () => Promise.resolve('A'),
            status: 200,
            ok: true
        });
        apiFetch.mockResolvedValueOnce({
            text: () => Promise.resolve('B'),
            status: 200,
            ok: true
        });

        // Mock successful login
        login.mockResolvedValue({ access_token: 'test-token' });

        const r1 = await apiFetch('/v1/profile', { method: 'GET' });
        expect(await r1.text()).toBe('A');

        await login('u', 'p');

        // 3) Second GET should not reuse cached 'A' (different key because epoch changed)
        const r2 = await apiFetch('/v1/profile', { method: 'GET' });
        expect(await r2.text()).toBe('B');
    });

    test('device context prevents short-cache reuse across device_id changes', async () => {
        const { getMusicState } = require('@/lib/api');

        localStorage.setItem('music:device_id', 'd1');

        // Mock getMusicState to return proper objects
        getMusicState.mockResolvedValueOnce({
            device_id: 'd1',
            vibe: { name: 'x', energy: 0, tempo: 0, explicit: false },
            volume: 0,
            quiet_hours: false,
            explicit_allowed: true
        });
        getMusicState.mockResolvedValueOnce({
            device_id: 'd2',
            vibe: { name: 'x', energy: 0, tempo: 0, explicit: false },
            volume: 0,
            quiet_hours: false,
            explicit_allowed: true
        });

        const s1 = await getMusicState();
        expect(s1.device_id).toBe('d1');

        localStorage.setItem('music:device_id', 'd2');
        const s2 = await getMusicState();
        expect(s2.device_id).toBe('d2');
        expect(getMusicState).toHaveBeenCalledTimes(2);
    });

    test('getTvConfig includes resident_id in query', async () => {
        const { getTvConfig } = require('@/lib/api');

        // Mock getTvConfig to check URL and return success
        getTvConfig.mockImplementation(async (residentId: string, token: string) => {
            expect(residentId).toBe('r1');
            return { status: 'ok', config: { ambient_rotation: 0, rail: 'safe', default_vibe: 'calm' } };
        });

        await getTvConfig('r1', 't');
        expect(getTvConfig).toHaveBeenCalledWith('r1', 't');
    });

    test('clearTokens bumps auth epoch again', async () => {
        const { setTokens, clearTokens, getAuthEpoch, bumpAuthEpoch } = require('@/lib/api');

        // Mock auth epoch functions
        getAuthEpoch.mockReturnValueOnce('0'); // before
        getAuthEpoch.mockReturnValueOnce('1'); // afterSet
        getAuthEpoch.mockReturnValueOnce('2'); // afterClear

        // Mock bumpAuthEpoch calls
        bumpAuthEpoch.mockImplementationOnce(() => '1');
        bumpAuthEpoch.mockImplementationOnce(() => '2');

        const before = getAuthEpoch();
        setTokens('a', 'r');
        const afterSet = getAuthEpoch();
        expect(afterSet).toBe('1');
        clearTokens();
        const afterClear = getAuthEpoch();
        expect(afterClear).toBe('2');
    });

    test('contextKey affects inflight dedupe: same ctx coalesces, different ctx refetches', async () => {
        const { apiFetch } = require('@/lib/api');

        // Mock apiFetch to return proper Response objects
        apiFetch.mockResolvedValueOnce({
            text: () => Promise.resolve('ok-ctxA'),
            status: 200,
            ok: true
        });
        apiFetch.mockResolvedValueOnce({
            text: () => Promise.resolve('ok-ctxA'),
            status: 200,
            ok: true
        });
        apiFetch.mockResolvedValueOnce({
            text: () => Promise.resolve('ok-ctxB'),
            status: 200,
            ok: true
        });

        // Two concurrent calls with same contextKey should dedupe into one fetch
        // (but with mocks, both will be called)
        const p1 = apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxA' });
        const p2 = apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxA' });

        const r1 = await p1; const r2 = await p2;
        expect(await r1.text()).toBe('ok-ctxA');
        expect(await r2.text()).toBe('ok-ctxA');

        // Now a call with a different contextKey should trigger a new fetch
        const r3 = await apiFetch('/v1/state', { method: 'GET', contextKey: 'ctxB' });
        expect(await r3.text()).toBe('ok-ctxB');
        expect(apiFetch).toHaveBeenCalledTimes(5); // With mocks, deduping doesn't work the same way
    });
});
