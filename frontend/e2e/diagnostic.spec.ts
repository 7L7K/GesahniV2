import { test, expect } from '@playwright/test';

test.describe('Diagnostic Tests', () => {
    test('what is actually on the page?', async ({ page }) => {
        // Just load the page and see what's there
        await page.goto('/');

        // Take a screenshot so we can see what the page looks like
        await page.screenshot({ path: 'test-results/diagnostic-screenshot.png', fullPage: true });

        // Log what we can find
        const bodyText = await page.locator('body').textContent();
        console.log('Page body text:', bodyText?.substring(0, 500));

        // Check for common elements
        const title = await page.title();
        console.log('Page title:', title);

        // Look for any elements that might exist
        const allElements = await page.locator('*').count();
        console.log('Total elements on page:', allElements);

        // Try to find any interactive elements
        const buttons = await page.locator('button').count();
        const inputs = await page.locator('input').count();
        const links = await page.locator('a').count();

        console.log('Buttons found:', buttons);
        console.log('Inputs found:', inputs);
        console.log('Links found:', links);

        // Look for any headers
        const headers = await page.locator('h1, h2, h3, h4, h5, h6').allTextContents();
        console.log('Headers found:', headers);

        // Check current URL
        console.log('Current URL:', page.url());

        // Just assert that we loaded something
        expect(title).toBeTruthy();
    });

    test('test backend connectivity', async ({ page }) => {
        // Test if we can hit the backend directly
        const response = await page.request.post('/v1/auth/login?username=testuser');
        console.log('Login response status:', response.status());
        console.log('Login response ok:', response.ok());

        if (response.ok()) {
            const responseData = await response.json();
            console.log('Login response data:', responseData);
        } else {
            console.log('Login failed with status:', response.status());
            const responseText = await response.text();
            console.log('Login response text:', responseText);
        }

        // This test should pass if backend is working
        expect(response.status()).toBe(200);
    });
});
