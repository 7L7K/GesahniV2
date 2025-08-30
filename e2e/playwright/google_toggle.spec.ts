import { test, expect } from '@playwright/test';

test.describe('Google service toggles', () => {
  test('enable gmail success updates status', async ({ page }) => {
    // Mock enable service endpoint
    await page.route('**/v1/google/service/gmail/enable', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, service: 'gmail', state: 'enabled' }) });
    });
    // Mock status endpoint to show gmail enabled
    await page.route('**/v1/google/status', route => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ connected: true, scopes: ['https://www.googleapis.com/auth/gmail.readonly'], expires_at: null }) });
    });

    await page.goto('http://localhost:3000/settings');
    // Open Google manage drawer
    await page.click('text=Google');
    await page.click('text=Manage');
    // Click enable Gmail
    await page.click('button:has-text("Enable")');
    // Expect toast success or updated badge
    await expect(page.locator('text=enabled')).toBeVisible({ timeout: 3000 });
  });

  test('enable gmail rollback on account_mismatch shows modal', async ({ page }) => {
    // Return an envelope with account_mismatch
    await page.route('**/v1/google/service/gmail/enable', route => {
      route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ code: 'account_mismatch', message: 'Google account mismatch', details: { error_id: 'ERR123' } }) });
    });
    await page.goto('http://localhost:3000/settings');
    await page.click('text=Google');
    await page.click('text=Manage');
    await page.click('button:has-text("Enable")');
    // Modal should appear
    await expect(page.locator('text=Account Mismatch')).toBeVisible({ timeout: 3000 });
  });
});

