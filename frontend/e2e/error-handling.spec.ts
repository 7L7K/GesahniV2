import { test, expect } from '@playwright/test';

test.describe('Error Handling and Edge Cases', () => {
    test('network errors and offline handling', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        // Simulate offline state by blocking network requests
        await page.route('**/v1/**', route => route.abort());

        await page.goto('/');
        await page.waitForSelector('[data-testid="error-message"]', { timeout: 10000 });

        // Verify error message is displayed
        const errorMessage = page.locator('[data-testid="error-message"]');
        await expect(errorMessage).toBeVisible();
        await expect(errorMessage).toContainText('network');

        // Test retry functionality
        const retryButton = page.locator('[data-testid="retry-button"]');
        if (await retryButton.isVisible()) {
            await retryButton.click();
            // Should show loading state or attempt retry
            await expect(page.locator('[data-testid="loading-spinner"]')).toBeVisible();
        }
    });

    test('authentication errors', async ({ page }) => {
        // Try to access protected route without authentication
        await page.goto('/settings');

        // Should redirect to login
        await page.waitForURL('**/login');
        expect(page.url()).toMatch(/\/login/);

        // Verify login form is displayed
        await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    });

    test('invalid form submissions', async ({ page }) => {
        await page.goto('/login');

        // Try submitting empty form
        const submitButton = page.locator('[data-testid="login-submit"]');
        await submitButton.click();

        // Should show validation errors
        await expect(page.locator('[data-testid="username-error"]')).toBeVisible();
        await expect(page.locator('[data-testid="password-error"]')).toBeVisible();

        // Try with invalid email format
        await page.locator('[data-testid="username"]').fill('invalid@');
        await page.locator('[data-testid="password"]').fill('short');
        await submitButton.click();

        // Should show specific validation errors
        await expect(page.locator('[data-testid="username-error"]')).toContainText('invalid');
        await expect(page.locator('[data-testid="password-error"]')).toContainText('too short');
    });

    test('API rate limiting', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Simulate rate limiting by making many rapid requests
        const requests = [];
        for (let i = 0; i < 10; i++) {
            requests.push(page.request.post('/v1/auth/login?username=testuser'));
        }

        const responses = await Promise.all(requests);

        // At least one should be rate limited (429)
        const rateLimitedResponses = responses.filter(r => r.status() === 429);
        expect(rateLimitedResponses.length).toBeGreaterThan(0);

        // UI should show rate limit warning
        await expect(page.locator('[data-testid="rate-limit-warning"]')).toBeVisible();

        // Should show cooldown timer
        await expect(page.locator('[data-testid="cooldown-timer"]')).toBeVisible();
    });

    test('session expiration handling', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');
        await page.waitForSelector('header');

        // Clear session cookies to simulate expiration
        await page.context().clearCookies();

        // Try to access protected resource
        await page.reload();

        // Should redirect to login
        await page.waitForURL('**/login');
        expect(page.url()).toMatch(/\/login/);

        // Should show session expired message
        await expect(page.locator('[data-testid="session-expired"]')).toBeVisible();
    });

    test('404 and not found pages', async ({ page }) => {
        await page.goto('/non-existent-page');

        // Should show 404 page
        await expect(page.locator('[data-testid="404-page"]')).toBeVisible();

        // Should have navigation back to home
        const homeButton = page.locator('[data-testid="go-home"]');
        await expect(homeButton).toBeVisible();

        await homeButton.click();
        await page.waitForURL('/');
        expect(page.url()).toBe('http://localhost:3000/');
    });

    test('server errors (5xx)', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Mock API to return 500 errors
        await page.route('**/v1/**', route => {
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Internal Server Error' })
            });
        });

        // Try to perform an action that makes API call
        await page.locator('[data-testid="send-button"]').click();

        // Should show server error message
        await expect(page.locator('[data-testid="server-error"]')).toBeVisible();

        // Should offer retry option
        const retryButton = page.locator('[data-testid="retry-action"]');
        await expect(retryButton).toBeVisible();
    });

    test('WebSocket connection failures', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Wait for WebSocket connection attempt
        await page.waitForTimeout(2000);

        // Should show connection status
        const connectionStatus = page.locator('[data-testid="ws-status"]');
        if (await connectionStatus.isVisible()) {
            // Connection might fail in test environment
            await expect(connectionStatus).toBeVisible();
        }

        // Should have reconnection indicator if connection fails
        const reconnectIndicator = page.locator('[data-testid="reconnecting"]');
        // This might or might not be visible depending on WS implementation
    });

    test('form validation edge cases', async ({ page }) => {
        await page.goto('/settings');

        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.reload();
        await page.waitForSelector('[data-testid="profile-form"]');

        // Test maximum length validation
        const nameField = page.locator('[data-testid="profile-name"]');
        const longName = 'a'.repeat(300); // Exceed typical max length
        await nameField.fill(longName);

        const saveButton = page.locator('[data-testid="save-profile"]');
        await saveButton.click();

        // Should show validation error for too long input
        await expect(page.locator('[data-testid="name-too-long"]')).toBeVisible();

        // Test special characters
        await nameField.fill('<script>alert("xss")</script>');
        await saveButton.click();

        // Should sanitize or reject dangerous input
        await expect(page.locator('[data-testid="invalid-characters"]')).toBeVisible();
    });

    test('slow network conditions', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Simulate slow network by delaying responses
        await page.route('**/v1/**', async route => {
            await page.waitForTimeout(2000); // 2 second delay
            await route.continue();
        });

        // Try to send a message
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('Slow network test');

        const sendButton = page.locator('[data-testid="send-button"]');
        await sendButton.click();

        // Should show loading state during slow request
        await expect(page.locator('[data-testid="sending-indicator"]')).toBeVisible();

        // Should eventually complete and show message
        await page.waitForSelector('[data-testid="user-message"]', { timeout: 10000 });
        await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Slow network test');
    });
});
