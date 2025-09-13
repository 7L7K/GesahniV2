import { test, expect } from '@playwright/test';

test('proxy mode uses relative URLs (no absolute backend origin)', async ({ page, context }) => {
  // Skip if proxy mode is disabled
  const useProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'true') === 'true';
  test.skip(!useProxy, 'proxy mode disabled');

  const requests: string[] = [];
  page.on('request', (req) => { requests.push(req.url()); });

  await page.goto('/debug/env-canary');
  await page.waitForSelector('pre');

  // Ensure no requests hit http://localhost:8000 or http://127.0.0.1:8000 directly
  const forbidden = requests.filter(u => /https?:\/\/(localhost|127\.0\.0\.1):8000\//.test(u));
  expect(forbidden).toEqual([]);
});
