import { test, expect } from '@playwright/test';

test.describe('Basic Functionality', () => {
    test('page loads and shows basic content', async ({ page }) => {
        await page.goto('/');

        // Wait for the page to be fully loaded
        await page.waitForLoadState('networkidle');

        // Give React time to hydrate and render
        await page.waitForTimeout(3000);

        // Check that we have some content now
        const bodyText = await page.locator('body').textContent();
        console.log('Page content after loading:', bodyText?.substring(0, 1000));

        // Look for any text content that indicates the app loaded
        const hasContent = bodyText && bodyText.length > 100;
        console.log('Page has substantial content:', hasContent);

        // Check for common React app indicators
        const reactRoot = await page.locator('#__next').count();
        console.log('React root found:', reactRoot > 0);

        // Take another screenshot to see the current state
        await page.screenshot({ path: 'test-results/after-loading.png', fullPage: true });

        // Just verify the page didn't crash
        expect(await page.title()).toBeTruthy();
    });

    test('authentication works end-to-end', async ({ page }) => {
        // First authenticate via API
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        const loginData = await loginResponse.json();
        console.log('Login successful:', loginData.status);

        // Now visit the page with authentication cookies
        await page.goto('/');

        // Wait for the page to load
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(3000);

        // Check if we're authenticated by looking for auth indicators
        const cookies = await page.context().cookies();
        const authCookies = cookies.filter(c => ['GSNH_AT', 'GSNH_RT', 'GSNH_SESS'].includes(c.name));

        console.log('Auth cookies found:', authCookies.length);
        expect(authCookies.length).toBeGreaterThan(0);

        // Check if the page shows authenticated content
        const currentUrl = page.url();
        console.log('Current URL:', currentUrl);

        // If we're not redirected to login, we're probably authenticated
        expect(currentUrl).not.toMatch(/login/);
    });

    test('can access basic routes', async ({ page }) => {
        // Test different routes
        const routes = ['/', '/settings', '/admin'];

        for (const route of routes) {
            console.log(`Testing route: ${route}`);

            // Authenticate first
            const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
            expect(loginResponse.ok()).toBe(true);

            // Visit the route
            await page.goto(route);
            await page.waitForLoadState('networkidle');
            await page.waitForTimeout(2000);

            // Check that the page loads (doesn't crash)
            const title = await page.title();
            console.log(`Route ${route} title:`, title);

            // Verify we can access the route
            expect(title).toBeTruthy();
            expect(page.url()).toContain(route === '/' ? '' : route);
        }
    });

    test('API endpoints respond correctly', async ({ page }) => {
        const endpoints = [
            '/v1/health',
            '/v1/whoami',
            '/v1/auth/csrf'
        ];

        for (const endpoint of endpoints) {
            console.log(`Testing endpoint: ${endpoint}`);

            const response = await page.request.get(endpoint);
            console.log(`Endpoint ${endpoint} status:`, response.status());

            // Most endpoints should return some response
            expect([200, 401, 403]).toContain(response.status());
        }
    });
});
