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
        expect(res.status).toBe(400);
        expect(window.localStorage.getItem("auth:access_token")).toBeNull();
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
        localStorage.setItem('auth:access_token', 't');
        await apiFetch('/v1/test');
        const [url, init] = (global.fetch as any).mock.calls[0];
        expect((init.headers as any).Authorization).toBe('Bearer t');
        expect(url).toContain('/v1/test');
    });

    test('apiFetch tries refresh on 401 and clears tokens if failed', async () => {
        (global as any).fetch
            .mockImplementationOnce(async () => new Response('no', { status: 401 } as any) as any)
            .mockImplementationOnce(async () => new Response('no', { status: 401 } as any) as any);
        localStorage.setItem('auth:refresh_token', 'r');
        await apiFetch('/v1/x').catch(() => undefined);
        // tokens should be cleared after failed refresh
        expect(localStorage.getItem('auth:access_token')).toBeNull();
    });

    test('wsUrl appends token as query', () => {
        localStorage.setItem('auth:access_token', 'tok');
        const url = wsUrl('/v1/stream');
        expect(url).toMatch(/access_token=/);
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

    test('setTokens and clearTokens dispatch events', () => {
        const setSpy = jest.fn();
        const clearSpy = jest.fn();
        window.addEventListener('auth:tokens_set', setSpy);
        window.addEventListener('auth:tokens_cleared', clearSpy);
        setTokens('a', 'r');
        clearTokens();
        expect(setSpy).toHaveBeenCalled();
        expect(clearSpy).toHaveBeenCalled();
    });
});


