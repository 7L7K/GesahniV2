// Test script to check what headers are being sent
const { chromium } = require('playwright');

async function testHeaders() {
  console.log('🔍 Testing request headers...');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    baseURL: 'http://localhost:3000'
  });

  const page = await context.newPage();

  // Listen for requests
  page.on('request', request => {
    if (request.url().includes('/v1/csrf')) {
      console.log('📤 CSRF Request headers:');
      console.log('  Origin:', request.headers()['origin']);
      console.log('  Referer:', request.headers()['referer']);
      console.log('  Host:', request.headers()['host']);
      console.log('  x-csrf-token:', request.headers()['x-csrf-token']);
      console.log('  All headers:', Object.keys(request.headers()));
    }

    if (request.url().includes('/v1/auth/login')) {
      console.log('📤 Login Request headers:');
      console.log('  Origin:', request.headers()['origin']);
      console.log('  Referer:', request.headers()['referer']);
      console.log('  Host:', request.headers()['host']);
      console.log('  x-csrf-token:', request.headers()['x-csrf-token']);
      console.log('  Cookie:', request.headers()['cookie']);
      console.log('  All headers:', Object.keys(request.headers()));
    }
  });

  try {
    // Navigate to a page first to establish the context
    await page.goto('http://localhost:3000');

    // Test with page.request (like Playwright test does)
    console.log('🧪 Testing with page.request (like Playwright test)...');
    const csrfResponse = await page.request.get('/v1/csrf');
    const csrfData = await csrfResponse.json();
    const csrfToken = csrfData.csrf_token;

    console.log('🔑 Got CSRF token:', csrfToken);

    const loginResponse = await page.request.post('/v1/auth/login?username=test_user', {
      headers: {
        'x-csrf-token': csrfToken,
        'Origin': 'http://localhost:3000'  // Add Origin header explicitly
      }
    });

    console.log('📥 Login response status:', loginResponse.status());

    if (!loginResponse.ok()) {
      const errorText = await loginResponse.text();
      console.log('❌ Login error:', errorText);
    } else {
      console.log('✅ Login successful!');
      const loginData = await loginResponse.json();
      console.log('📋 Login response data keys:', Object.keys(loginData));
    }


  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testHeaders().catch(console.error);
