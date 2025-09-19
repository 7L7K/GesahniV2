// Test script to verify login flow authentication state updates immediately
const { chromium } = require('playwright');

async function testLoginFlow() {
  console.log('🚀 Starting login flow test...');

  const browser = await chromium.launch({
    headless: false, // Set to true for headless mode
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    baseURL: 'http://localhost:3000'
  });

  const page = await context.newPage();

  try {
    console.log('📝 Navigating to login page...');
    await page.goto('/login');

    // Wait for the page to load
    await page.waitForSelector('input[name="username"]');
    console.log('✅ Login page loaded');

    // Fill in login credentials
    await page.fill('input[name="username"]', 'test_user');
    await page.fill('input[name="password"]', 'dummy_password');

    // Click login button
    const loginButton = page.locator('button[type="submit"]').filter({ hasText: 'Sign In' });
    await loginButton.click();

    console.log('🔐 Login submitted, waiting for navigation...');

    // Wait for navigation to complete (should redirect to dashboard)
    await page.waitForURL('http://localhost:3000/', { timeout: 10000 });

    console.log('✅ Navigation completed');

    // Check if we're authenticated by looking for logout button
    const logoutButton = page.locator('button').filter({ hasText: 'Logout' });
    const isAuthenticated = await logoutButton.isVisible();

    if (isAuthenticated) {
      console.log('✅ SUCCESS: Authentication state updated immediately after login');
      console.log('🎉 User is properly authenticated and logout button is visible');
    } else {
      console.log('❌ FAILURE: Authentication state not updated properly');
      console.log('🔍 Logout button not found - user may not be authenticated');
    }

    // Additional check: look for user ID in the UI
    const userBadge = page.locator('text=Connected as test_user');
    const hasUserBadge = await userBadge.isVisible();

    if (hasUserBadge) {
      console.log('✅ SUCCESS: User information is displayed correctly');
    } else {
      console.log('⚠️ WARNING: User information not found in UI');
    }

  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testLoginFlow().catch(console.error);
