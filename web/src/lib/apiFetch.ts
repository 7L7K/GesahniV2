export type ApiError = { status: number; message: string };

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function sleep(ms: number) {
    return new Promise((r) => setTimeout(r, ms));
}

export async function apiFetch<T>(
    input: string,
    init: RequestInit = {},
    opts: { retries?: number } = {}
): Promise<T> {
    const url = input.startsWith("http") ? input : `${BASE_URL}${input}`;
    const headers: HeadersInit = {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init.headers || {}),
    };

    const retries = Math.max(0, opts.retries ?? 2);
    let attempt = 0;
    let lastErr: unknown;

    while (attempt <= retries) {
        try {
            const res = await fetch(url, { ...init, headers, credentials: "include" });
            if (!res.ok) {
                // transient? 429/502/503/504 with backoff
                if ([429, 502, 503, 504].includes(res.status) && attempt < retries) {
                    const retryAfter = Number(res.headers.get("Retry-After") || "0");
                    await sleep(retryAfter ? retryAfter * 1000 : (attempt + 1) * 300);
                    attempt += 1;
                    continue;
                }
                const body = await safeJson(res);
                const err: ApiError = { status: res.status, message: extractMessage(body) };
                throw err;
            }
            return (await safeJson(res)) as T;
        } catch (e) {
            lastErr = e;
            if (attempt < retries) {
                await sleep((attempt + 1) * 300);
                attempt += 1;
                continue;
            }
            throw e;
        }
    }
    throw lastErr as Error;
}

async function safeJson(res: Response): Promise<unknown> {
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) return await res.text();
    try {
        return await res.json();
    } catch {
        return {};
    }
}

function extractMessage(body: unknown): string {
    if (!body) return "error";
    if (typeof body === "string") return body.slice(0, 200);
    try {
        const obj = body as any;
        return (
            obj?.detail?.message || obj?.detail || obj?.error || obj?.message || "error"
        );
    } catch {
        return "error";
    }
}


