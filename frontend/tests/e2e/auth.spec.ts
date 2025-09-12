import { test, expect } from '@playwright/test';

const API = process.env.NEXT_PUBLIC_API_ORIGIN || 'http://127.0.0.1:8000';

test.describe('Auth flow', () => {
    test('pre-auth whoami 401, post-login 200, logout 401', async ({ request, page }) => {
        const whoami1 = await request.get(`${API}/v1/whoami`);
        expect(whoami1.status()).toBe(401);

        await page.goto('/login');
        await page.fill('input#username', 'demo');
        await page.fill('input#password', 'demo');
        await page.click('button[type="submit"]');

        // wait for session badge to flip
        await page.waitForSelector('[data-testid="session-badge"]');

        const whoami2 = await request.get(`${API}/v1/whoami`);
        expect(whoami2.status()).toBe(200);

        // logout via button
        await page.click('text=Logout');
        const whoami3 = await request.get(`${API}/v1/whoami`);
        expect([401, 403]).toContain(whoami3.status());
    });
});


