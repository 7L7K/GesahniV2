import { test, expect, request } from '@playwright/test';

const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || 'http://localhost:3000';

test.describe('Dev login flow (proxy same-origin)', () => {
  test('csrf → login → whoami and cookie attributes', async ({ browser }) => {
    // API client pinned to front-end origin (Next dev server)
    const api = await request.newContext({
      baseURL: FRONTEND_ORIGIN,
      extraHTTPHeaders: { 'Accept': 'application/json' },
    });

    // 1) CSRF
    const csrfRes = await api.get('/v1/csrf');
    expect(csrfRes.ok()).toBeTruthy();
    const csrfJson = await csrfRes.json().catch(() => ({} as any));
    const csrf =
      csrfJson?.csrf_token ||
      csrfRes.headers()['x-csrf-token'] ||
      '';
    expect(typeof csrf).toBe('string');
    expect(String(csrf).length).toBeGreaterThan(0);

    // 2) Login (dev path)
    const loginRes = await api.post('/v1/auth/login?username=playwright', {
      headers: { 'x-csrf-token': String(csrf) },
    });
    expect(loginRes.ok()).toBeTruthy();
    const setCookie = loginRes.headersArray().filter(h => h.name.toLowerCase() === 'set-cookie');
    expect(setCookie.length).toBeGreaterThan(0);

    // 3) whoami
    const who = await api.get('/v1/whoami');
    expect(who.status()).toBe(200);
    const whoJson = await who.json();
    expect(whoJson?.is_authenticated).toBe(true);
    expect(whoJson?.session_ready).toBe(true);
    expect(whoJson?.user?.id || whoJson?.user_id).toBe('playwright');

    // 4) Cookie attributes (dev: host-only, Path=/, Lax, HttpOnly, NOT Secure)
    const context = await browser.newContext({ baseURL: FRONTEND_ORIGIN });
    const page = await context.newPage();
    await page.goto(FRONTEND_ORIGIN + '/');
    const cookies = await context.cookies(FRONTEND_ORIGIN);
    const byName = (n: string) => cookies.find(c => c.name === n);

    const names = ['GSNH_AT', 'GSNH_RT', 'GSNH_SESS'];
    for (const base of names) {
      const c = byName(base) || byName(`__Host-${base}`);
      expect(c, `cookie ${base} present`).toBeTruthy();
      expect(c!.path).toBe('/');
      expect(c!.sameSite).toBe('Lax');
      expect(c!.httpOnly).toBe(true);
      expect(c!.secure).toBe(false);
    }

    await context.close();
  });
});
