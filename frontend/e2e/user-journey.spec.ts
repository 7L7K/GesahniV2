import { test, expect } from '@playwright/test';

test.describe('Complete User Journey', () => {
    test('full authentication and navigation flow', async ({ page }) => {
        // Start at homepage
        await page.goto('/');

        // Should redirect to login if not authenticated
        await page.waitForURL('**/login');
        expect(page.url()).toMatch(/\/login/);

        // Login via backend API (test harness)
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        // Navigate to dashboard
        await page.goto('/');
        await page.waitForSelector('header');

        // Verify authenticated UI
        const header = page.locator('header');
        await expect(header).toBeVisible();

        // Check for navigation elements
        await expect(page.locator('nav')).toBeVisible();
        await expect(page.locator('text=Chat')).toBeVisible();
        await expect(page.locator('text=Settings')).toBeVisible();

        // Test navigation to settings
        await page.click('text=Settings');
        await page.waitForURL('**/settings');
        expect(page.url()).toMatch(/\/settings/);

        // Test navigation back to chat
        await page.click('text=Chat');
        await page.waitForURL('**/');
        expect(page.url()).toMatch(/^((?!login).)*$/); // Not login page
    });

    test('logout functionality', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');
        await page.waitForSelector('header');

        // Click logout
        await page.click('text=Logout');

        // Should redirect to login
        await page.waitForURL('**/login');
        expect(page.url()).toMatch(/\/login/);

        // Verify cookies are cleared
        const cookies = await page.context().cookies();
        const authCookies = cookies.filter(c => ['GSNH_AT', 'GSNH_RT', 'GSNH_SESS'].includes(c.name));
        expect(authCookies.length).toBe(0);
    });
});
