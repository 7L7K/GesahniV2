import { test, expect } from '@playwright/test';

test.describe('Performance Tests', () => {
    test('page load performance', async ({ page }) => {
        // Measure page load time
        const startTime = Date.now();

        await page.goto('/', { waitUntil: 'networkidle' });
        const loadTime = Date.now() - startTime;

        // Page should load within reasonable time (under 3 seconds)
        expect(loadTime).toBeLessThan(3000);

        // Check for performance metrics
        const metrics = await page.evaluate(() => {
            const perfData = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
            return {
                domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
                loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
                firstPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-paint')?.startTime,
                firstContentfulPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-contentful-paint')?.startTime
            };
        });

        // First Contentful Paint should be reasonable
        if (metrics.firstContentfulPaint) {
            expect(metrics.firstContentfulPaint).toBeLessThan(2000);
        }
    });

    test('bundle size and resource loading', async ({ page }) => {
        // Track network requests
        const requests: string[] = [];
        const resources: Array<{ url: string; size: number; duration: number }> = [];

        page.on('request', req => requests.push(req.url()));
        page.on('response', response => {
            const url = response.url();
            const headers = response.headers();
            const contentLength = headers['content-length'];

            if (contentLength) {
                resources.push({
                    url,
                    size: parseInt(contentLength),
                    duration: 0 // Would need timing API for this
                });
            }
        });

        await page.goto('/', { waitUntil: 'networkidle' });

        // Check for excessive resource loading
        const jsRequests = requests.filter(url => url.includes('.js'));
        const cssRequests = requests.filter(url => url.includes('.css'));

        // Shouldn't have too many JS/CSS files (indicating poor bundling)
        expect(jsRequests.length).toBeLessThan(10);
        expect(cssRequests.length).toBeLessThan(5);

        // Check total bundle size (rough estimate)
        const totalSize = resources.reduce((sum, res) => sum + res.size, 0);
        // Should be reasonable (under 5MB for modern web apps)
        expect(totalSize).toBeLessThan(5 * 1024 * 1024);
    });

    test('runtime performance - message sending', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');
        await page.waitForSelector('[data-testid="chat-input"]');

        // Measure message sending performance
        const input = page.locator('[data-testid="chat-input"]');
        const sendButton = page.locator('[data-testid="send-button"]');

        const sendTimes: number[] = [];

        for (let i = 0; i < 5; i++) {
            const startTime = Date.now();

            await input.fill(`Performance test message ${i + 1}`);
            await sendButton.click();

            // Wait for response
            await page.waitForSelector(`[data-testid="user-message"]:has-text("Performance test message ${i + 1}")`);

            const endTime = Date.now();
            sendTimes.push(endTime - startTime);

            // Clear for next test
            await page.waitForTimeout(500);
        }

        // Calculate average response time
        const avgTime = sendTimes.reduce((sum, time) => sum + time, 0) / sendTimes.length;

        // Should respond within reasonable time (under 5 seconds)
        expect(avgTime).toBeLessThan(5000);
    });

    test('memory usage and leaks', async ({ page }) => {
        // This is a basic test - in a real scenario you'd use Chrome DevTools Protocol
        await page.goto('/');

        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.reload();

        // Perform some actions that might cause memory issues
        for (let i = 0; i < 10; i++) {
            const input = page.locator('[data-testid="chat-input"]');
            await input.fill(`Memory test ${i + 1}`);
            await page.locator('[data-testid="send-button"]').click();
            await page.waitForTimeout(200);
        }

        // Check that the page is still responsive
        const input = page.locator('[data-testid="chat-input"]');
        await expect(input).toBeEnabled();

        // Verify no excessive memory usage indicators
        const performanceMetrics = await page.evaluate(() => {
            // Get basic memory info if available
            const memInfo = (performance as any).memory;
            return memInfo ? {
                used: memInfo.usedJSHeapSize,
                total: memInfo.totalJSHeapSize,
                limit: memInfo.jsHeapSizeLimit
            } : null;
        });

        if (performanceMetrics) {
            // Memory usage should be reasonable (under 100MB for this simple test)
            expect(performanceMetrics.used).toBeLessThan(100 * 1024 * 1024);
        }
    });

    test('concurrent user actions', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');
        await page.waitForSelector('[data-testid="chat-input"]');

        // Simulate rapid user actions
        const actions = [];

        for (let i = 0; i < 5; i++) {
            actions.push(
                page.locator('[data-testid="chat-input"]').fill(`Concurrent message ${i + 1}`),
                page.locator('[data-testid="send-button"]').click(),
                page.waitForTimeout(100)
            );
        }

        const startTime = Date.now();
        await Promise.all(actions);
        const totalTime = Date.now() - startTime;

        // All actions should complete within reasonable time
        expect(totalTime).toBeLessThan(3000);

        // Verify all messages were sent
        for (let i = 0; i < 5; i++) {
            await expect(page.locator(`[data-testid="user-message"]:has-text("Concurrent message ${i + 1}")`)).toBeVisible();
        }
    });

    test('large dataset handling', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Simulate large number of messages (this might require mocking API responses)
        const largeMessage = 'a'.repeat(10000); // 10KB message

        const input = page.locator('[data-testid="chat-input"]');
        await input.fill(largeMessage);

        const startTime = Date.now();
        await page.locator('[data-testid="send-button"]').click();

        // Should handle large messages without crashing
        await page.waitForSelector('[data-testid="user-message"]', { timeout: 10000 });
        const endTime = Date.now();

        // Should complete within reasonable time despite large payload
        expect(endTime - startTime).toBeLessThan(10000);

        // UI should remain responsive
        await expect(page.locator('[data-testid="chat-input"]')).toBeEnabled();
    });

    test('scrolling performance', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Add many messages to test scrolling (would need to mock or generate content)
        // For now, we'll test basic scrolling performance

        const scrollContainer = page.locator('[data-testid="chat-messages"]');

        if (await scrollContainer.isVisible()) {
            // Measure scroll performance
            const scrollStart = Date.now();

            // Scroll to bottom
            await scrollContainer.evaluate(el => el.scrollTo(0, el.scrollHeight));
            await page.waitForTimeout(100);

            // Scroll to top
            await scrollContainer.evaluate(el => el.scrollTo(0, 0));
            await page.waitForTimeout(100);

            const scrollEnd = Date.now();

            // Scrolling should be smooth (under 500ms for basic operations)
            expect(scrollEnd - scrollStart).toBeLessThan(500);
        }
    });

    test('WebSocket connection performance', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Wait for WebSocket connection
        await page.waitForTimeout(2000);

        // Check connection status indicator
        const wsStatus = page.locator('[data-testid="ws-status"]');
        if (await wsStatus.isVisible()) {
            const statusText = await wsStatus.textContent();

            // Should show connected or connecting status
            expect(statusText).toMatch(/connected|connecting/i);
        }

        // Test WebSocket message handling performance
        const startTime = Date.now();

        // Send a message that should trigger WebSocket activity
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('WebSocket performance test');
        await page.locator('[data-testid="send-button"]').click();

        // Wait for response via WebSocket
        await page.waitForSelector('[data-testid="assistant-message"]', { timeout: 15000 });

        const endTime = Date.now();

        // WebSocket response should be reasonably fast
        expect(endTime - startTime).toBeLessThan(10000);
    });
});
