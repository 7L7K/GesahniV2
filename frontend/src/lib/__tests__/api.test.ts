/** @jest-environment jsdom */
import { apiFetch, setTokens, clearTokens } from "@/lib/api";

const originalFetch = global.fetch;

beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(window.localStorage.__proto__, 'getItem');
    jest.spyOn(window.localStorage.__proto__, 'setItem');
    jest.spyOn(window.localStorage.__proto__, 'removeItem');
    (global as any).fetch = jest.fn();
    clearTokens();
});

afterEach(() => {
    (global as any).fetch = originalFetch;
    jest.useRealTimers();
    jest.restoreAllMocks();
    clearTokens();
});

describe("apiFetch", () => {
    it("does not set Content-Type on GET without body", async () => {
        (global.fetch as any).mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }));
        const res = await apiFetch("/v1/models", { method: "GET" });
        expect(res.status).toBe(200);
        const call = (global.fetch as jest.Mock).mock.calls[0];
        const headers = call[1]?.headers || {};
        expect(Object.keys(headers)).not.toContain("Content-Type");
    });

    it("sets Content-Type on POST with JSON body", async () => {
        (global.fetch as any).mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }));
        await apiFetch("/v1/login", { method: "POST", auth: false, body: JSON.stringify({ a: 1 }) });
        const call = (global.fetch as jest.Mock).mock.calls[0];
        const headers = call[1]?.headers || {};
        expect(headers["Content-Type"]).toBe("application/json");
    });

    it("retries once after 401 if refresh succeeds", async () => {
        setTokens("expired", "refresh-token");
        // first request returns 401
        (global.fetch as any)
            .mockResolvedValueOnce(new Response("Unauthorized", { status: 401 }))
            // refresh token call
            .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new", refresh_token: "r2" }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
            // retried request
            .mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }));

        const res = await apiFetch("/v1/profile", { method: "GET" });
        expect(res.status).toBe(200);
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(3);
    });

    it("clears tokens if refresh fails after 401", async () => {
        setTokens("expired", "refresh-token");
        (global.fetch as any)
            .mockResolvedValueOnce(new Response("Unauthorized", { status: 401 }))
            .mockResolvedValueOnce(new Response("Bad refresh", { status: 400 }));

        const res = await apiFetch("/v1/profile", { method: "GET" });
        // When refresh fails, we return the refresh error response
        expect([400, 401]).toContain(res.status);
        expect(window.localStorage.getItem("auth:access_token")).toBeNull();
    });

    it("429 with Retry-After delays once and retries", async () => {
        (global.fetch as any)
            .mockResolvedValueOnce(new Response("Too Many", { status: 429, headers: { 'Retry-After': '1' } }))
            .mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }));
        const p = apiFetch("/v1/models?case=429", { method: "GET" });
        await Promise.resolve();
        jest.advanceTimersByTime(1500);
        const res = await p;
        expect(res.status).toBe(200);
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(2);
    });

    it("does not retry 404/422/403", async () => {
        (global.fetch as any).mockResolvedValueOnce(new Response("not found", { status: 404 }));
        const res = await apiFetch("/v1/none", { method: "GET" });
        expect(res.status).toBe(404);
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(1);
    });

    it("5xx GETs do limited backoff retries and stop after cap", async () => {
        jest.spyOn(global.Math, 'random').mockReturnValue(0);
        (global.fetch as any)
            .mockResolvedValueOnce(new Response("boom", { status: 500 }))
            .mockResolvedValueOnce(new Response("boom", { status: 502 }))
            .mockResolvedValueOnce(new Response("ok", { status: 200 }));
        const p = apiFetch("/v1/state?case=5xx", { method: "GET" });
        await Promise.resolve();
        jest.advanceTimersByTime(800);
        const res = await p;
        expect(res.status).toBe(200);
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(3);
        ; (global.Math.random as any).mockRestore?.();
    });

    it("circuit breaker opens on repeated 5xx and pauses next attempt", async () => {
        jest.spyOn(global.Math, 'random').mockReturnValue(0);
        (global.fetch as any)
            .mockResolvedValueOnce(new Response("boom", { status: 500 }))
            .mockResolvedValueOnce(new Response("boom", { status: 500 }))
            .mockResolvedValueOnce(new Response("boom", { status: 500 }))
            .mockResolvedValueOnce(new Response("{}", { status: 200, headers: { 'Content-Type': 'application/json' } }));

        const p1 = apiFetch("/v1/state?break=1", { method: "GET" });
        await Promise.resolve();
        jest.advanceTimersByTime(800);
        await p1.catch(() => { });

        const p2 = apiFetch("/v1/state?break=1", { method: "GET" });
        await Promise.resolve();
        jest.advanceTimersByTime(600);
        const res = await p2;
        expect(res.status).toBe(200);
        expect((global.fetch as jest.Mock).mock.calls.length).toBe(4);
        ; (global.Math.random as any).mockRestore?.();
    });
});

import { apiFetch, sendPrompt, wsUrl, setTokens, clearTokens } from '@/lib/api';

describe('api.ts', () => {
    beforeEach(() => {
        (global as any).fetch = jest.fn(async (url: any, init: any) => {
            // default ok response
            return new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } } as any) as any;
        });
        localStorage.clear();
    });
    afterEach(() => { (global as any).fetch = undefined; });

    test('apiFetch attaches auth header when token present', async () => {
        localStorage.setItem('auth:access', 't');
        await apiFetch('/v1/test');
        const [url, init] = (global.fetch as any).mock.calls[0];
        expect((init.headers as any).Authorization).toBe('Bearer t');
        expect(url).toContain('/v1/test');
    });

    test('apiFetch tries refresh on 401 and clears tokens if failed', async () => {
        (global as any).fetch
            .mockImplementationOnce(async () => new Response('no', { status: 401 } as any) as any)
            .mockImplementationOnce(async () => new Response('no', { status: 401 } as any) as any);
        localStorage.setItem('auth:refresh', 'r');
        await apiFetch('/v1/x').catch(() => undefined);
        // tokens should be cleared after failed refresh
        expect(localStorage.getItem('auth:access')).toBeNull();
    });

    test('wsUrl appends token as query', () => {
        localStorage.setItem('auth:access', 'tok');
        const url = wsUrl('/v1/stream');
        expect(url).toMatch(/access_token=/);
        // WebSocket requirement: Should use canonical frontend origin
        expect(url).toMatch(/ws:\/\/localhost:3000/);
    });

    test('sendPrompt parses json response', async () => {
        (global as any).fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ response: 'hi' }), { status: 200, headers: { 'content-type': 'application/json' } } as any) as any);
        const res = await sendPrompt('x', 'auto');
        expect(res).toBe('hi');
    });

    test('sendPrompt streams SSE data events and calls onToken', async () => {
        const encoder = new TextEncoder();
        // Mock Response body.getReader() to push 2 SSE events
        (global as any).fetch.mockImplementationOnce(async () => {
            return {
                ok: true,
                headers: { get: () => 'text/event-stream' },
                body: {
                    getReader: () => {
                        let sent = 0;
                        return {
                            read: async () => {
                                if (sent === 0) {
                                    sent++;
                                    return { value: encoder.encode('data: a\n\n'), done: false };
                                }
                                if (sent === 1) {
                                    sent++;
                                    return { value: encoder.encode('data: b\n\n'), done: false };
                                }
                                return { value: undefined, done: true };
                            },
                        };
                    },
                },
            } as any;
        });
        const chunks: string[] = [];
        const res = await sendPrompt('x', 'auto', (c) => chunks.push(c));
        expect(chunks.join('')).toBe('ab');
        expect(res).toBe('ab');
    });

    test('setTokens and clearTokens work correctly', () => {
        setTokens('a', 'r');
        expect(localStorage.getItem('auth:access')).toBe('a');
        expect(localStorage.getItem('auth:refresh')).toBe('r');
        clearTokens();
        expect(localStorage.getItem('auth:access')).toBeNull();
        expect(localStorage.getItem('auth:refresh')).toBeNull();
    });

    test('apiFetch handles AbortError gracefully', async () => {
        // Mock fetch to throw AbortError
        const originalFetch = global.fetch;
        global.fetch = jest.fn().mockRejectedValue(new Error('AbortError'));
        (global.fetch as jest.Mock).mockImplementation(() => {
            const error = new Error('AbortError');
            error.name = 'AbortError';
            throw error;
        });

        try {
            await apiFetch('/v1/test');
        } catch (error) {
            expect(error).toBeInstanceOf(Error);
            expect((error as Error).name).toBe('AbortError');
        }

        global.fetch = originalFetch;
    });

    test('apiFetch handles AbortError in refresh flow', async () => {
        // Mock fetch to return 401 first, then throw AbortError on refresh
        const originalFetch = global.fetch;
        let callCount = 0;
        global.fetch = jest.fn().mockImplementation(() => {
            callCount++;
            if (callCount === 1) {
                return Promise.resolve(new Response('', { status: 401 }));
            } else {
                const error = new Error('AbortError');
                error.name = 'AbortError';
                throw error;
            }
        });

        setTokens('test-token', 'test-refresh');

        try {
            await apiFetch('/v1/test');
        } catch (error) {
            expect(error).toBeInstanceOf(Error);
            expect((error as Error).name).toBe('AbortError');
        }

        global.fetch = originalFetch;
    });
});
