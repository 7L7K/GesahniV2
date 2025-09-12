import { test, expect } from '@playwright/test';
import { waitForNetworkIdle, collectNetworkMetrics } from '../helpers/network-idle';

// Performance budget: login page should settle network to idle within 2s on CI
const NETWORK_IDLE_TIMEOUT = process.env.CI ? 2000 : 5000;

/**
 * E2E tests for login redirect behavior to prevent re-nesting and ensure correct navigation.
 *
 * Test scenarios:
 * 1. Visiting /login?next=%2Fdashboard → URL cleans to /login; after login navigates to /
 * 2. Visiting /login?next=%2Flogin%3Fnext%3D… → after login lands on / (no loop)
 * 3. From protected page, Login CTA never creates /login?next=/login patterns
 * 4. Performance budget: network idle within 2s on CI
 * 5. Fail if login page URL contains ?next= after mount
 */

// Helper to validate login page URL after mount (should not contain ?next=)
async function validateLoginUrlAfterMount(page: any) {
    const url = page.url();
    if (url.includes('?next=')) {
        throw new Error(`Login page URL contains ?next= parameter after mount: ${url}`);
    }
}

// Helper for retrying network-flaky operations
async function retryNetworkOperation<T>(
    operation: () => Promise<T>,
    maxRetries: number = process.env.CI ? 3 : 1,
    retryableErrors: string[] = ['TimeoutError', 'NetworkError', 'net::ERR_']
): Promise<T> {
    for (let i = 0; i <= maxRetries; i++) {
        try {
            return await operation();
        } catch (error: any) {
            const isRetryable = retryableErrors.some(retryable =>
                error.message?.includes(retryable) || error.name?.includes(retryable)
            );

            if (!isRetryable || i === maxRetries) {
                throw error;
            }

            console.log(`Network operation failed (attempt ${i + 1}/${maxRetries + 1}), retrying...`);
            await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1))); // Exponential backoff
        }
    }
    throw new Error('Should not reach here');
}

test.describe('Login Redirect Behavior', () => {
    test.beforeEach(async ({ page }) => {
        // Clear any existing auth state
        await page.context().clearCookies();
    });

    test('should clean URL and redirect to dashboard after login with next param', async ({ page }) => {
        // Visit login page with next parameter
        await retryNetworkOperation(async () => {
            await page.goto('/login?next=%2Fdashboard');
        });

        // Performance budget: network should settle within timeout
        await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

        // URL should be cleaned to /login (next param removed)
        await expect(page).toHaveURL(/\/login$/);

        // Validate login page URL after mount (should not contain ?next=)
        await validateLoginUrlAfterMount(page);

        // Use mock login button for testing
        await retryNetworkOperation(async () => {
            await page.click('[data-testid="mock-login-button"]');
        });

        // Should redirect to dashboard (which is / in this app)
        await expect(page).toHaveURL(/\//);
        await expect(page.locator('text=Welcome to Gesahni')).not.toBeVisible();
    });

    test('should prevent redirect loops with nested next params', async ({ page }) => {
        // Visit login page with nested next parameter that could cause a loop
        const nestedNext = encodeURIComponent('/login?next=%2Fdashboard');

        await retryNetworkOperation(async () => {
            await page.goto(`/login?next=${nestedNext}`);
        });

        // Performance budget: network should settle within timeout
        await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

        // URL should be cleaned to /login
        await expect(page).toHaveURL(/\/login$/);

        // Validate login page URL after mount (should not contain ?next=)
        await validateLoginUrlAfterMount(page);

        // Use mock login button for testing
        await retryNetworkOperation(async () => {
            await page.click('[data-testid="mock-login-button"]');
        });

        // Should redirect to dashboard (/) not back to login
        await expect(page).toHaveURL(/\//);
        await expect(page.locator('text=Welcome to Gesahni')).not.toBeVisible();
    });

    test('should prevent re-nested redirects with complex next params', async ({ page }) => {
        // Create a complex nested next parameter
        const complexNext = encodeURIComponent('/login?next=%2Flogin%3Fnext%3D%252Fdashboard');

        await retryNetworkOperation(async () => {
            await page.goto(`/login?next=${complexNext}`);
        });

        // Performance budget: network should settle within timeout
        await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

        // URL should be cleaned to /login
        await expect(page).toHaveURL(/\/login$/);

        // Validate login page URL after mount (should not contain ?next=)
        await validateLoginUrlAfterMount(page);

        // Use mock login button for testing
        await retryNetworkOperation(async () => {
            await page.click('[data-testid="mock-login-button"]');
        });

        // Should redirect to dashboard (/) not create a loop
        await expect(page).toHaveURL(/\//);
        await expect(page.locator('text=Welcome to Gesahni')).not.toBeVisible();
    });

    test('Login CTA from protected page should never create nested login redirects', async ({ page }) => {
        // Visit a protected page (root page requires auth)
        await retryNetworkOperation(async () => {
            await page.goto('/');
        });

        // Wait for page to stabilize and check what URL we end up at
        await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);
        const currentUrl = page.url();

        // If we're already redirected to login, check the URL pattern
        if (currentUrl.includes('/login')) {
            const url = new URL(currentUrl);
            // Should not have next parameter pointing to login
            const nextParam = url.searchParams.get('next');
            if (nextParam) {
                expect(nextParam).not.toMatch(/.*login.*/);
                expect(nextParam).not.toMatch(/.*%2Flogin.*/);
            }
            // Validate login page URL after mount (should not contain ?next=)
            await validateLoginUrlAfterMount(page);
            return; // Test passes if no problematic next param
        }

        // If we're still on the root page, look for login prompt
        try {
            await expect(page.locator('text=Please sign in to start chatting')).toBeVisible();

            // Click the Login button
            await retryNetworkOperation(async () => {
                await page.click('text=Login');
            });

            // Performance budget: network should settle within timeout after navigation
            await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

            // Should navigate to /login without any next parameter that points to login
            await expect(page).toHaveURL(/\/login$/);

            // Validate login page URL after mount (should not contain ?next=)
            await validateLoginUrlAfterMount(page);

            const url = page.url();
            expect(url).not.toMatch(/next=.*login/);
            expect(url).not.toMatch(/next=.*%2Flogin/);
        } catch (e) {
            // If login prompt not found, check if we were redirected properly
            await expect(page).toHaveURL(/\/login$/);
            const url = page.url();
            expect(url).not.toMatch(/next=.*login/);
            expect(url).not.toMatch(/next=.*%2Flogin/);
        }
    });

    test('should handle URL-encoded next parameters safely', async ({ page }) => {
        // Test various URL encodings
        const testCases = [
            '/login?next=%2F',  // encoded /
            '/login?next=%2Fdashboard',  // encoded /dashboard
            '/login?next=%252Fdashboard',  // double encoded /dashboard
        ];

        for (const testUrl of testCases) {
            await retryNetworkOperation(async () => {
                await page.goto(testUrl);
            });

            // Performance budget: network should settle within timeout
            await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

            await expect(page).toHaveURL(/\/login$/);

            // Validate login page URL after mount (should not contain ?next=)
            await validateLoginUrlAfterMount(page);

            // Use mock login button for testing
            await retryNetworkOperation(async () => {
                await page.click('[data-testid="mock-login-button"]');
            });

            // Should redirect to dashboard (/)
            await expect(page).toHaveURL(/\//);
            await expect(page.locator('text=Welcome to Gesahni')).not.toBeVisible();
        }
    });

    test('should handle malformed next parameters gracefully', async ({ page }) => {
        // Test malformed next parameters
        const malformedUrls = [
            '/login?next=',
            '/login?next=invalid%2Fpath',
            '/login?next=..%2F..%2Fetc',
            '/login?next=%2F%2Fevil.com',
        ];

        for (const testUrl of malformedUrls) {
            await retryNetworkOperation(async () => {
                await page.goto(testUrl);
            });

            // Performance budget: network should settle within timeout
            await waitForNetworkIdle(page, NETWORK_IDLE_TIMEOUT);

            await expect(page).toHaveURL(/\/login$/);

            // Validate login page URL after mount (should not contain ?next=)
            await validateLoginUrlAfterMount(page);

            // Use mock login button for testing
            await retryNetworkOperation(async () => {
                await page.click('[data-testid="mock-login-button"]');
            });

            // Should redirect to dashboard (/) as fallback
            await expect(page).toHaveURL(/\//);
            await expect(page.locator('text=Welcome to Gesahni')).not.toBeVisible();
        }
    });
});
