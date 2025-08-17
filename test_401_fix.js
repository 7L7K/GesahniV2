// Test script to verify 401 error fix
// This script simulates the auth flow and checks for 401 errors

const puppeteer = require('puppeteer');

async function test401Fix() {
    console.log('Starting 401 error fix test...');

    const browser = await puppeteer.launch({
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();

    // Listen for network requests and log 401s
    const requests = [];
    page.on('response', response => {
        if (response.status() === 401) {
            requests.push({
                url: response.url(),
                status: response.status(),
                timestamp: new Date().toISOString()
            });
            console.log(`❌ 401 Error: ${response.url()}`);
        }
    });

    try {
        // Navigate to the app
        console.log('Navigating to app...');
        await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });

        // Wait a bit for any initial requests
        await page.waitForTimeout(3000);

        // Check if there were any 401 errors
        if (requests.length === 0) {
            console.log('✅ No 401 errors detected during initial load');
        } else {
            console.log(`❌ Found ${requests.length} 401 errors:`);
            requests.forEach(req => {
                console.log(`   - ${req.url} at ${req.timestamp}`);
            });
        }

        // Check if music state is loaded (should not cause 401)
        const musicStateLoaded = await page.evaluate(() => {
            return window.musicState !== undefined;
        });

        console.log(`Music state loaded: ${musicStateLoaded}`);

    } catch (error) {
        console.error('Test failed:', error);
    } finally {
        await browser.close();
    }
}

// Run the test
test401Fix().catch(console.error);
