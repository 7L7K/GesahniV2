import { test } from '@playwright/test';

// Placeholder end-to-end coverage for auth cookie behavior.
// A full implementation requires running backend + frontend with real credentials.
// Marked as skipped so CI can explicitly opt-in when environment is ready.

test.describe.skip('auth cookies integration', () => {
  test('login sets cookies and bearer fallback works', async () => {
    test.skip();
  });
});
