import { test, expect, APIRequestContext, APIResponse } from '@playwright/test';

type WhoamiPayload = {
    is_authenticated?: boolean;
    authenticated?: boolean;
    session_ready?: boolean;
    user?: { id?: string | null } | null;
    user_id?: string | null;
};

function isAuthenticated(payload: WhoamiPayload): boolean {
    if (typeof payload?.is_authenticated === 'boolean') return payload.is_authenticated;
    if (typeof payload?.authenticated === 'boolean') return payload.authenticated;
    if (typeof payload?.user_id === 'string' && payload.user_id.length > 0) return true;
    if (payload?.user && typeof payload.user.id === 'string' && payload.user.id.length > 0) return true;
    return false;
}

async function loginAsAdmin(request: APIRequestContext): Promise<void> {
    const csrfRes = await request.get('/v1/csrf');
    expect(csrfRes.ok()).toBeTruthy();
    const csrf = csrfRes.headers()['x-csrf-token'];
    expect(csrf).toBeTruthy();

    const loginRes = await request.post('/v1/auth/login', {
        data: { username: 'admin', password: 'ChangeMe!' },
        headers: { 'x-csrf-token': csrf as string },
    });
    expect(loginRes.ok()).toBeTruthy();
}

async function expectUnauthenticated(res: APIResponse) {
    const status = res.status();
    expect([200, 401]).toContain(status);
    if (status === 200) {
        const payload = (await res.json()) as WhoamiPayload;
        expect(isAuthenticated(payload)).toBe(false);
    }
}

async function expectAuthenticated(res: APIResponse) {
    expect(res.status()).toBe(200);
    const payload = (await res.json()) as WhoamiPayload;
    expect(isAuthenticated(payload)).toBe(true);
}

test('logout clears auth and whoami is fresh', async ({ page }) => {
    const ctxRequest = page.context().request;
    await loginAsAdmin(ctxRequest);

    const initialWhoami = await ctxRequest.get('/v1/auth/whoami');
    await expectAuthenticated(initialWhoami);

    await page.goto('/logout');
    await page.waitForURL('**/login?logout=1');

    const freshWhoami = await ctxRequest.fetch('/v1/auth/whoami', {
        headers: { 'cache-control': 'no-store' },
    });
    await expectUnauthenticated(freshWhoami);
});

test('whoami has no-store headers', async ({ page }) => {
    const res = await page.context().request.get('/v1/auth/whoami');
    expect(res.ok()).toBeTruthy();

    const headers = res.headers();
    expect(headers['cache-control']).toContain('no-store');
    expect(headers['pragma']).toBe('no-cache');
    expect(headers['expires']).toBe('0');
});

test('multi-tab logout has no stale auth', async ({ browser, request }) => {
    await loginAsAdmin(request);
    const storageState = await request.storageState();
    const baseURL = test.info().project.use?.baseURL ?? 'http://localhost:3000';

    const ctxA = await browser.newContext({ storageState, baseURL });
    const ctxB = await browser.newContext({ storageState, baseURL });

    try {
        const pageA = await ctxA.newPage();
        const pageB = await ctxB.newPage();

        await pageA.goto(`${baseURL}/dashboard`);
        await pageB.goto(`${baseURL}/dashboard`);

        await pageA.goto(`${baseURL}/logout`);
        await pageA.waitForURL('**/login?logout=1');

        await pageB.reload({ waitUntil: 'networkidle' });

        await expectUnauthenticated(await ctxA.request.get('/v1/auth/whoami'));
        await expectUnauthenticated(await ctxB.request.get('/v1/auth/whoami'));
    } finally {
        await ctxA.close();
        await ctxB.close();
    }
});
