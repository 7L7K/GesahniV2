import { test, expect } from '@playwright/test';

test('login → whoami → no orchestrator crash', async ({ page, request }) => {
    // health should be reachable without auth
    const h = await request.get('http://localhost:8000/v1/health');
    expect(h.ok()).toBeTruthy();

    await page.goto('http://localhost:3000/login');
    await page.getByLabel(/username/i).fill('admin');
    await page.getByLabel(/password/i).fill('ChangeMe!');
    await page.getByRole('button', { name: /log in/i }).click();

    await page.waitForURL(/dashboard|chat|\/$/, { timeout: 15000 });

    // Ensure no orchestrator import crash
    const errors: string[] = [];
    page.on('console', msg => {
        if (msg.type() === 'error') errors.push(msg.text());
    });

    // Whoami should be happy
    const res = await page.request.get('http://localhost:8000/v1/whoami', { headers: { 'X-Auth-Orchestrator': 'legitimate' } });
    expect(res.ok()).toBeTruthy();

    // Give HMR/import a second to settle
    await page.waitForTimeout(500);

    // No “Cannot access uninitialized variable”
    const crash = errors.find(e => /uninitialized variable/i.test(e));
    expect(crash).toBeFalsy();
});
