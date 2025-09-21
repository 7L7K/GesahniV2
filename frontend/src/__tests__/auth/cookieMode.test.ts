/**
 * Comprehensive test plan for cookie-mode authentication
 * Can be adapted for Cypress/Playwright
 */

import { test, expect, beforeEach } from '@playwright/test';

// Test configuration
const API_URL = process.env.TEST_API_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.TEST_FRONTEND_URL || 'http://localhost:3000';

test.describe('Cookie Mode Authentication', () => {
    beforeEach(async ({ page }) => {
        // Set cookie mode explicitly
        await page.addInitScript(() => {
            window.__AUTH_MODE_OVERRIDE = 'cookie';
        });
    });

    test.describe('Basic Authentication Flow', () => {
        test('successful login sets HTTP-only cookies', async ({ page }) => {
            await page.goto(`${FRONTEND_URL}/login`);

            // Fill login form
            await page.fill('[data-testid="username"]', 'testuser');
            await page.fill('[data-testid="password"]', 'testpass');

            // Monitor network requests
            const loginRequest = page.waitForRequest(`${API_URL}/v1/auth/login`);
            await page.click('[data-testid="login-button"]');

            const request = await loginRequest;
            expect(request.method()).toBe('POST');
            expect(request.headers()['content-type']).toContain('application/json');

            // Check response sets cookies
            const response = await request.response();
            expect(response?.status()).toBe(200);

            const setCookieHeaders = response?.headers()['set-cookie'] || '';
            expect(setCookieHeaders).toContain('GSNH_AT=');
            expect(setCookieHeaders).toContain('HttpOnly');
            expect(setCookieHeaders).toContain('SameSite=Lax');

            // Verify redirect to dashboard
            await expect(page).toHaveURL(`${FRONTEND_URL}/`);
        });

        test('whoami endpoint works with cookies', async ({ page, context }) => {
            // First login to set cookies
            await loginUser(page);

            // Make whoami request and verify it uses cookies
            const whoamiRequest = page.waitForRequest(`${API_URL}/v1/auth/whoami`);
            await page.goto(`${FRONTEND_URL}/`);

            const request = await whoamiRequest;
            expect(request.headers()['cookie']).toContain('GSNH_AT=');
            expect(request.headers()['authorization']).toBeUndefined();

            const response = await request.response();
            const body = await response?.json();
            expect(body.is_authenticated).toBe(true);
            expect(body.user_id).toBe('testuser');
            expect(body.source).toBe('cookie');
        });

        test('logout clears cookies and redirects', async ({ page }) => {
            await loginUser(page);

            // Trigger logout
            const logoutRequest = page.waitForRequest(`${API_URL}/v1/auth/logout`);
            await page.click('[data-testid="logout-button"]');

            const request = await logoutRequest;
            expect(request.method()).toBe('POST');

            // Verify logout response clears cookies
            const response = await request.response();
            const setCookieHeaders = response?.headers()['set-cookie'] || '';
            expect(setCookieHeaders).toContain('GSNH_AT=;'); // Empty cookie

            // Verify redirect to login
            await expect(page).toHaveURL(`${FRONTEND_URL}/login`);
        });
    });

    test.describe('Error Handling', () => {
        test('network error shows graceful message', async ({ page }) => {
            // Block network requests to simulate offline
            await page.route(`${API_URL}/v1/auth/whoami`, route => route.abort());

            await page.goto(`${FRONTEND_URL}/`);

            // Should show network error message, not crash
            await expect(page.locator('[data-testid="auth-error"]')).toContainText(
                'Unable to connect to server'
            );

            // Should show login option
            await expect(page.locator('[data-testid="login-link"]')).toBeVisible();
        });

        test('expired cookies trigger re-authentication', async ({ page }) => {
            await loginUser(page);

            // Simulate expired cookies by returning 401
            await page.route(`${API_URL}/v1/auth/whoami`, route => {
                route.fulfill({
                    status: 401,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: 'Token expired' })
                });
            });

            await page.reload();

            // Should redirect to login
            await expect(page).toHaveURL(`${FRONTEND_URL}/login`);

            // Should show appropriate message
            await expect(page.locator('[data-testid="auth-message"]')).toContainText(
                'Session expired'
            );
        });

        test('handles missing CSRF token gracefully', async ({ page }) => {
            await page.goto(`${FRONTEND_URL}/login`);

            // Block CSRF endpoint
            await page.route(`${API_URL}/v1/csrf`, route => route.abort());

            await page.fill('[data-testid="username"]', 'testuser');
            await page.click('[data-testid="login-button"]');

            // Should show CSRF error
            await expect(page.locator('[data-testid="error-message"]')).toContainText(
                'Failed to get CSRF token'
            );
        });
    });

    test.describe('Safari/iOS Compatibility', () => {
        test('works in Safari private mode simulation', async ({ page, context }) => {
            // Simulate Safari private mode by blocking some storage
            await page.addInitScript(() => {
                // Override localStorage to throw errors (Safari private mode behavior)
                const originalSetItem = localStorage.setItem;
                localStorage.setItem = function (key: string, value: string) {
                    if (key.startsWith('__private_test_')) {
                        throw new Error('QuotaExceededError');
                    }
                    return originalSetItem.call(this, key, value);
                };
            });

            await loginUser(page);

            // Verify authentication still works
            await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
        });

        test('handles SameSite cookie restrictions', async ({ page, context }) => {
            // Test cross-origin scenario
            await page.goto(`${FRONTEND_URL}/login`);

            // Check that cookies are set with proper SameSite attributes
            const cookies = await context.cookies();
            const authCookie = cookies.find(c => c.name === 'GSNH_AT');

            if (authCookie) {
                expect(authCookie.sameSite).toBe('Lax');
            }
        });
    });

    test.describe('Cookie Expiry and Refresh', () => {
        test('handles access token refresh mid-session', async ({ page }) => {
            await loginUser(page);

            // Wait for initial whoami to complete
            await page.waitForSelector('[data-testid="user-menu"]');

            // Mock a refresh scenario by making the next whoami return new tokens
            await page.route(`${API_URL}/v1/auth/whoami`, (route, request) => {
                const response = {
                    status: 200,
                    contentType: 'application/json',
                    headers: {
                        'set-cookie': [
                            'GSNH_AT=new_access_token; HttpOnly; SameSite=Lax; Max-Age=900',
                            'GSNH_RT=new_refresh_token; HttpOnly; SameSite=Lax; Max-Age=2592000'
                        ]
                    },
                    body: JSON.stringify({
                        is_authenticated: true,
                        session_ready: true,
                        user_id: 'testuser',
                        source: 'cookie'
                    })
                };
                route.fulfill(response);
            });

            // Trigger a refresh by navigating
            await page.reload();

            // Should still be authenticated
            await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
        });

        test('handles refresh token expiry gracefully', async ({ page }) => {
            await loginUser(page);

            // Simulate refresh token expiry
            await page.route(`${API_URL}/v1/auth/whoami`, route => {
                route.fulfill({
                    status: 401,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: 'Refresh token expired' })
                });
            });

            await page.reload();

            // Should redirect to login
            await expect(page).toHaveURL(`${FRONTEND_URL}/login`);
        });
    });

    test.describe('Mode Switching', () => {
        test('can switch from cookie to header mode', async ({ page }) => {
            // Start in cookie mode
            await loginUser(page);

            // Switch to header mode
            await page.evaluate(() => {
                window.__AUTH_MODE_OVERRIDE = 'header';
            });

            // Trigger mode switch
            await page.click('[data-testid="refresh-auth"]');

            // Verify next requests use Authorization header
            const nextRequest = page.waitForRequest(`${API_URL}/v1/auth/whoami`);
            await page.reload();

            const request = await nextRequest;
            expect(request.headers()['authorization']).toContain('Bearer ');
            expect(request.headers()['cookie']).not.toContain('GSNH_AT=');
        });

        test('automatically falls back to header mode if cookies fail', async ({ page, context }) => {
            // Block cookies in browser
            await context.route(`${API_URL}/v1/csrf`, route => {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({ csrf_token: 'test_token' }),
                    headers: {
                        // No set-cookie header
                    }
                });
            });

            // Set up header tokens manually
            await page.addInitScript(() => {
                localStorage.setItem('auth:access', 'test_header_token');
            });

            await page.goto(`${FRONTEND_URL}/`);

            // Should automatically use header mode
            const whoamiRequest = page.waitForRequest(`${API_URL}/v1/auth/whoami`);
            await page.waitForTimeout(1000);

            const request = await whoamiRequest;
            expect(request.headers()['authorization']).toContain('Bearer test_header_token');
        });
    });

    test.describe('Performance and Edge Cases', () => {
        test('handles rapid auth state changes without oscillation', async ({ page }) => {
            await loginUser(page);

            // Rapidly trigger auth checks
            for (let i = 0; i < 5; i++) {
                await page.click('[data-testid="refresh-auth"]');
                await page.waitForTimeout(100);
            }

            // Should not crash or show errors
            await expect(page.locator('[data-testid="auth-error"]')).not.toBeVisible();
            await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
        });

        test('handles concurrent auth requests', async ({ page }) => {
            await page.goto(`${FRONTEND_URL}/login`);

            // Trigger multiple concurrent login attempts
            const promises = Array.from({ length: 3 }, async () => {
                await page.fill('[data-testid="username"]', 'testuser');
                await page.fill('[data-testid="password"]', 'testpass');
                return page.click('[data-testid="login-button"]');
            });

            await Promise.allSettled(promises);

            // Should end up authenticated without errors
            await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
        });
    });
});

// Helper functions
async function loginUser(page: any) {
    await page.goto(`${FRONTEND_URL}/login`);
    await page.fill('[data-testid="username"]', 'testuser');
    await page.fill('[data-testid="password"]', 'testpass');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL(`${FRONTEND_URL}/`);
}
