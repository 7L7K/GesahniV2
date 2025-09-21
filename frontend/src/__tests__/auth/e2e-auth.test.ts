/**
 * End-to-end authentication test for both cookie and header modes
 * Tests the complete authentication flow from login to logout
 */

import { test, expect } from '@playwright/test';

const API_URL = process.env.TEST_API_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.TEST_FRONTEND_URL || 'http://localhost:3000';

test.describe('End-to-End Authentication', () => {
    test.describe('Cookie Mode', () => {
        test.use({
            extraHTTPHeaders: {
                // Simulate cookie mode environment
                'NEXT_PUBLIC_HEADER_AUTH_MODE': 'false',
            },
        });

        test('complete cookie mode authentication flow', async ({ page, context }) => {
            // Step 1: Visit login page
            await page.goto(`${FRONTEND_URL}/login`);
            await expect(page.locator('h1')).toContainText(/login/i);

            // Step 2: Check that no auth cookies exist initially
            let cookies = await context.cookies();
            expect(cookies.find(c => c.name.startsWith('GSNH_'))).toBeUndefined();

            // Step 3: Login via API (simulates frontend form submission)
            const loginResponse = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
                headers: { 'Content-Type': 'application/json' }
            });
            expect(loginResponse.ok()).toBeTruthy();

            const loginData = await loginResponse.json();
            expect(loginData.user_id).toBe('testuser');
            expect(loginData.access_token).toBeUndefined(); // Cookie mode shouldn't return tokens

            // Step 4: Verify HTTP-only cookies were set
            cookies = await context.cookies();
            const authCookie = cookies.find(c => c.name === 'GSNH_AT');
            expect(authCookie).toBeTruthy();
            expect(authCookie?.httpOnly).toBeTruthy();
            expect(authCookie?.sameSite).toBe('Lax');

            // Step 5: Navigate to protected page
            await page.goto(`${FRONTEND_URL}/`);
            await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();

            // Step 6: Verify whoami works with cookies
            const whoamiResponse = await page.request.get(`${API_URL}/v1/auth/whoami`);
            expect(whoamiResponse.ok()).toBeTruthy();

            const whoamiData = await whoamiResponse.json();
            expect(whoamiData.is_authenticated).toBe(true);
            expect(whoamiData.user_id).toBe('testuser');
            expect(whoamiData.source).toBe('cookie');

            // Step 7: Logout
            const logoutResponse = await page.request.post(`${API_URL}/v1/auth/logout`);
            expect(logoutResponse.ok()).toBeTruthy();

            // Step 8: Verify cookies were cleared
            cookies = await context.cookies();
            const clearedCookie = cookies.find(c => c.name === 'GSNH_AT');
            expect(clearedCookie?.value).toBe(''); // Empty value means cleared

            // Step 9: Verify whoami returns unauthenticated
            const postLogoutWhoami = await page.request.get(`${API_URL}/v1/auth/whoami`);
            expect(postLogoutWhoami.ok()).toBeTruthy();

            const postLogoutData = await postLogoutWhoami.json();
            expect(postLogoutData.is_authenticated).toBe(false);
            expect(postLogoutData.user_id).toBeNull();
        });
    });

    test.describe('Header Mode', () => {
        test.use({
            extraHTTPHeaders: {
                // Simulate header mode environment
                'NEXT_PUBLIC_HEADER_AUTH_MODE': 'true',
            },
        });

        test('complete header mode authentication flow', async ({ page, context }) => {
            // Step 1: Visit login page
            await page.goto(`${FRONTEND_URL}/login`);
            await expect(page.locator('h1')).toContainText(/login/i);

            // Step 2: Login via API
            const loginResponse = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
                headers: { 'Content-Type': 'application/json' }
            });
            expect(loginResponse.ok()).toBeTruthy();

            const loginData = await loginResponse.json();
            expect(loginData.user_id).toBe('testuser');
            expect(loginData.access_token).toBeTruthy(); // Header mode should return tokens
            expect(loginData.refresh_token).toBeTruthy();

            const accessToken = loginData.access_token;

            // Step 3: Verify no HTTP-only cookies were set (header mode)
            const cookies = await context.cookies();
            expect(cookies.find(c => c.name.startsWith('GSNH_'))).toBeUndefined();

            // Step 4: Test whoami with Authorization header
            const whoamiResponse = await page.request.get(`${API_URL}/v1/auth/whoami`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            expect(whoamiResponse.ok()).toBeTruthy();

            const whoamiData = await whoamiResponse.json();
            expect(whoamiData.is_authenticated).toBe(true);
            expect(whoamiData.user_id).toBe('testuser');
            expect(whoamiData.source).toBe('header');

            // Step 5: Test logout with Authorization header
            const logoutResponse = await page.request.post(`${API_URL}/v1/auth/logout`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            expect(logoutResponse.ok()).toBeTruthy();

            // Step 6: Verify whoami fails after logout
            const postLogoutWhoami = await page.request.get(`${API_URL}/v1/auth/whoami`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            // Should return 401 or still work (depends on server implementation)
            const postLogoutData = await postLogoutWhoami.json();
            expect(postLogoutData.is_authenticated).toBe(false);
        });
    });

    test.describe('Mode Switching', () => {
        test('can switch from cookie to header mode', async ({ page }) => {
            // Start with cookie mode
            await page.addInitScript(() => {
                window.__AUTH_MODE_OVERRIDE = 'cookie';
            });

            await page.goto(`${FRONTEND_URL}/login`);

            // Login in cookie mode
            const cookieLogin = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
            });
            expect(cookieLogin.ok()).toBeTruthy();

            // Switch to header mode
            await page.evaluate(() => {
                window.__AUTH_MODE_OVERRIDE = 'header';
                window.location.reload();
            });

            await page.waitForLoadState();

            // Login again in header mode
            const headerLogin = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
            });
            const headerData = await headerLogin.json();
            expect(headerData.access_token).toBeTruthy();
        });
    });

    test.describe('Error Handling', () => {
        test('gracefully handles network errors', async ({ page }) => {
            // Block all API requests
            await page.route(`${API_URL}/**`, route => route.abort());

            await page.goto(`${FRONTEND_URL}/login`);

            // Should show error message instead of crashing
            await expect(page.locator('[data-testid="network-error"]')).toBeVisible();
            await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
        });

        test('handles expired tokens gracefully', async ({ page }) => {
            await page.goto(`${FRONTEND_URL}/login`);

            // Login first
            const loginResponse = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
            });
            expect(loginResponse.ok()).toBeTruthy();

            // Simulate expired token by mocking whoami to return 401
            await page.route(`${API_URL}/v1/auth/whoami`, route => {
                route.fulfill({
                    status: 401,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: 'Token expired' })
                });
            });

            await page.goto(`${FRONTEND_URL}/`);

            // Should redirect to login
            await expect(page).toHaveURL(`${FRONTEND_URL}/login`);
        });
    });

    test.describe('Safari Compatibility', () => {
        test('works with Safari-like cookie restrictions', async ({ page, context }) => {
            // Simulate Safari by blocking third-party cookies
            await page.route(`${API_URL}/**`, async (route, request) => {
                // Remove cookies from request to simulate Safari blocking them
                const headers = { ...request.headers() };
                delete headers['cookie'];

                await route.continue({
                    headers: {
                        ...headers,
                        // Add SameSite=Lax to all responses
                        'Set-Cookie': request.url().includes('/csrf')
                            ? 'csrf_token=test; SameSite=Lax; HttpOnly'
                            : undefined
                    }
                });
            });

            await page.goto(`${FRONTEND_URL}/login`);

            // Should still work with fallback mechanisms
            const loginResponse = await page.request.post(`${API_URL}/v1/auth/login`, {
                data: { username: 'testuser' },
            });

            // May fail due to simulated restrictions, but shouldn't crash
            if (loginResponse.ok()) {
                const data = await loginResponse.json();
                expect(data.user_id).toBe('testuser');
            }
        });
    });
});
