import { expect, request, test } from '@playwright/test';

const API_ORIGIN = process.env.API_ORIGIN || 'http://127.0.0.1:8000';

test.describe('Legacy auth redirects', () => {
  test('legacy root /login redirects with deprecation headers', async () => {
    const api = await request.newContext({
      baseURL: API_ORIGIN,
      extraHTTPHeaders: {
        Accept: 'application/json',
      },
    });

    const response = await api.post('/login', {
      data: {},
      failOnStatusCode: false,
      headers: { 'Content-Type': 'application/json' },
      // Don't follow redirects to test the redirect response itself
      maxRedirects: 0
    });
    expect(response.status()).toBe(308);

    const headers = response.headers();
    expect(headers['location']).toMatch(/^\/v1\/auth\/login/);
    expect(headers['deprecation']).toBeTruthy();
    expect(headers['sunset']).toMatch(/Wed, 31 Dec 2025 23:59:59 GMT/);

    await api.dispose();
  });
});
