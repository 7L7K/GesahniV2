import { test, expect } from '@playwright/test';

test.describe('Admin Functionality', () => {
    test.beforeEach(async ({ page }) => {
        // Setup admin session (assuming admin user exists)
        const loginResponse = await page.request.post('/v1/auth/login?username=admin');
        expect(loginResponse.ok()).toBe(true);
        await page.goto('/admin');
        await page.waitForSelector('[data-testid="admin-dashboard"]');
    });

    test('admin dashboard access', async ({ page }) => {
        // Verify admin dashboard loads
        await expect(page.locator('[data-testid="admin-dashboard"]')).toBeVisible();

        // Check for admin navigation
        await expect(page.locator('[data-testid="admin-nav"]')).toBeVisible();

        // Verify admin-only elements are present
        await expect(page.locator('[data-testid="admin-metrics"]')).toBeVisible();
        await expect(page.locator('[data-testid="system-status"]')).toBeVisible();
    });

    test('admin metrics display', async ({ page }) => {
        // Navigate to metrics tab
        await page.click('[data-testid="admin-metrics-tab"]');

        // Wait for metrics to load
        await page.waitForSelector('[data-testid="metrics-container"]');

        // Check for key metrics
        const metricsContainer = page.locator('[data-testid="metrics-container"]');
        await expect(metricsContainer).toBeVisible();

        // Verify metrics data is displayed
        await expect(page.locator('[data-testid="user-count"]')).toBeVisible();
        await expect(page.locator('[data-testid="session-count"]')).toBeVisible();
        await expect(page.locator('[data-testid="api-requests"]')).toBeVisible();
    });

    test('system status monitoring', async ({ page }) => {
        // Navigate to system status
        await page.click('[data-testid="system-status-tab"]');

        // Wait for status indicators
        await page.waitForSelector('[data-testid="backend-status"]');

        // Check backend status
        const backendStatus = page.locator('[data-testid="backend-status"]');
        await expect(backendStatus).toBeVisible();

        // Check database status
        const dbStatus = page.locator('[data-testid="database-status"]');
        await expect(dbStatus).toBeVisible();

        // Check WebSocket status
        const wsStatus = page.locator('[data-testid="websocket-status"]');
        await expect(wsStatus).toBeVisible();
    });

    test('user management', async ({ page }) => {
        // Navigate to user management
        await page.click('[data-testid="user-management-tab"]');

        // Wait for user list
        await page.waitForSelector('[data-testid="user-list"]');

        // Check user list is displayed
        const userList = page.locator('[data-testid="user-list"]');
        await expect(userList).toBeVisible();

        // Test user search/filter
        const searchInput = page.locator('[data-testid="user-search"]');
        if (await searchInput.isVisible()) {
            await searchInput.fill('test');
            await page.waitForSelector('[data-testid="user-item"]');
        }

        // Test user actions (view, edit, delete)
        const firstUser = page.locator('[data-testid="user-item"]').first();
        if (await firstUser.isVisible()) {
            await firstUser.click();

            // Verify user details modal/page
            await expect(page.locator('[data-testid="user-details"]')).toBeVisible();
        }
    });

    test('error monitoring and logging', async ({ page }) => {
        // Navigate to error logs
        await page.click('[data-testid="error-logs-tab"]');

        // Wait for error logs to load
        await page.waitForSelector('[data-testid="error-list"]');

        // Check error list is displayed
        const errorList = page.locator('[data-testid="error-list"]');
        await expect(errorList).toBeVisible();

        // Test error filtering
        const filterSelect = page.locator('[data-testid="error-filter"]');
        if (await filterSelect.isVisible()) {
            await filterSelect.selectOption('error');
            await page.waitForSelector('[data-testid="error-item"]');
        }

        // Test error details view
        const firstError = page.locator('[data-testid="error-item"]').first();
        if (await firstError.isVisible()) {
            await firstError.click();

            // Verify error details
            await expect(page.locator('[data-testid="error-details"]')).toBeVisible();
            await expect(page.locator('[data-testid="error-stacktrace"]')).toBeVisible();
        }
    });

    test('configuration management', async ({ page }) => {
        // Navigate to configuration
        await page.click('[data-testid="config-tab"]');

        // Wait for config options
        await page.waitForSelector('[data-testid="config-section"]');

        // Check configuration sections
        const configSection = page.locator('[data-testid="config-section"]');
        await expect(configSection).toBeVisible();

        // Test configuration updates
        const saveButton = page.locator('[data-testid="save-config"]');
        if (await saveButton.isVisible()) {
            // Make a configuration change
            const maxUsersInput = page.locator('[data-testid="max-users"]');
            if (await maxUsersInput.isVisible()) {
                await maxUsersInput.fill('100');

                // Save configuration
                await saveButton.click();

                // Verify success message
                await expect(page.locator('[data-testid="config-saved"]')).toBeVisible();
            }
        }
    });

    test('self-review functionality', async ({ page }) => {
        // Navigate to self-review
        await page.click('[data-testid="self-review-tab"]');

        // Wait for self-review content
        await page.waitForSelector('[data-testid="self-review-content"]');

        // Check self-review is displayed
        const selfReview = page.locator('[data-testid="self-review-content"]');
        await expect(selfReview).toBeVisible();

        // Test self-review interactions
        const reviewActions = page.locator('[data-testid="review-action"]');
        if (await reviewActions.count() > 0) {
            await reviewActions.first().click();

            // Verify action was recorded
            await expect(page.locator('[data-testid="action-recorded"]')).toBeVisible();
        }
    });

    test('admin security and access control', async ({ page }) => {
        // Test that non-admin users cannot access admin routes
        // This would require testing with a regular user session

        // Verify admin token is present
        const adminToken = await page.evaluate(() => {
            return localStorage.getItem('admin_token') || sessionStorage.getItem('admin_token');
        });

        if (adminToken) {
            // Verify admin token is valid
            const tokenValidation = await page.request.get('/v1/admin/status', {
                headers: { 'Authorization': `Bearer ${adminToken}` }
            });

            expect(tokenValidation.ok()).toBe(true);
        }

        // Test admin action logging
        await page.click('[data-testid="admin-action"]');

        // Verify action was logged
        await expect(page.locator('[data-testid="action-logged"]')).toBeVisible();
    });
});
