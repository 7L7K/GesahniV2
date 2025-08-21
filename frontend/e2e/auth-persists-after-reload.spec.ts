import { test, expect } from '@playwright/test';

test('auth persists after reload', async ({ page }) => {
    // Start at login page (or homepage which redirects to login)
    await page.goto('/');

    // Trigger login via backend dev login flow, if available
    // This depends on test harness exposing a login helper route; adjust as needed.
    const loginRes = await page.request.post('/v1/auth/login?username=playwright');
    expect(loginRes.ok()).toBeTruthy();

    // Wait for app shell to appear (header/profile avatar element)
    await page.waitForSelector('header');

    // Reload twice
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Ensure authenticated UI present (profile/avatar)
    const avatar = await page.$('header [data-testid="profile-avatar"]');
    expect(avatar).not.toBeNull();

    // Inspect cookies for canonical names only
    const cookies = await page.context().cookies();
    const names = cookies.map(c => c.name);
    expect(names).toContain('GSNH_AT');
    expect(names).toContain('GSNH_RT');
    expect(names).toContain('GSNH_SESS');
    expect(names).not.toContain('access_token');
    expect(names).not.toContain('refresh_token');
    expect(names).not.toContain('__session');
});


