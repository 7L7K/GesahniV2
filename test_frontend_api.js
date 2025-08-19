#!/usr/bin/env node
/**
 * Test script to verify frontend API configuration and connection
 * This simulates what the frontend would do
 */

const https = require('https');
const http = require('http');

// Frontend environment variables (from .env.local)
const FRONTEND_CONFIG = {
    NEXT_PUBLIC_SITE_URL: 'http://localhost:3000',
    NEXT_PUBLIC_API_ORIGIN: 'http://localhost:8000',
    NEXT_PUBLIC_HEADER_AUTH_MODE: '1'
};

async function makeRequest(url, options = {}) {
    return new Promise((resolve, reject) => {
        const urlObj = new URL(url);
        const client = urlObj.protocol === 'https:' ? https : http;

        const req = client.request(url, {
            method: options.method || 'GET',
            headers: options.headers || {},
            ...options
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const jsonData = JSON.parse(data);
                    resolve({ status: res.statusCode, data: jsonData, headers: res.headers });
                } catch {
                    resolve({ status: res.statusCode, data, headers: res.headers });
                }
            });
        });

        req.on('error', reject);

        if (options.body) {
            req.write(options.body);
        }

        req.end();
    });
}

async function testFrontendAPI() {
    console.log('🔧 Testing Frontend API Configuration');
    console.log('='.repeat(50));
    console.log('Frontend Config:', FRONTEND_CONFIG);
    console.log('');

    try {
        // Test 1: Basic API connection
        console.log('1️⃣ Testing basic API connection...');
        const whoamiResult = await makeRequest(`${FRONTEND_CONFIG.NEXT_PUBLIC_API_ORIGIN}/v1/whoami`, {
            headers: {
                'Origin': FRONTEND_CONFIG.NEXT_PUBLIC_SITE_URL,
                'Content-Type': 'application/json'
            }
        });

        if (whoamiResult.status === 200) {
            console.log('✅ API connection successful');
            console.log('   Response:', whoamiResult.data);
        } else {
            console.log('❌ API connection failed:', whoamiResult.status);
        }

        // Test 2: Login flow
        console.log('\n2️⃣ Testing login flow...');
        const loginResult = await makeRequest(`${FRONTEND_CONFIG.NEXT_PUBLIC_API_ORIGIN}/v1/login`, {
            method: 'POST',
            headers: {
                'Origin': FRONTEND_CONFIG.NEXT_PUBLIC_SITE_URL,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: 'testuser',
                password: 'testpass123'
            })
        });

        if (loginResult.status === 200 && loginResult.data.access_token) {
            console.log('✅ Login successful');
            console.log('   Token length:', loginResult.data.access_token.length);

            // Test 3: Authenticated request
            console.log('\n3️⃣ Testing authenticated request...');
            const authResult = await makeRequest(`${FRONTEND_CONFIG.NEXT_PUBLIC_API_ORIGIN}/v1/whoami`, {
                headers: {
                    'Origin': FRONTEND_CONFIG.NEXT_PUBLIC_SITE_URL,
                    'Authorization': `Bearer ${loginResult.data.access_token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (authResult.status === 200 && authResult.data.is_authenticated) {
                console.log('✅ Authenticated request successful');
                console.log('   User:', authResult.data.user.id);
                console.log('   Source:', authResult.data.source);
            } else {
                console.log('❌ Authenticated request failed:', authResult.status);
            }
        } else {
            console.log('❌ Login failed:', loginResult.status);
        }

        // Test 4: CORS headers
        console.log('\n4️⃣ Testing CORS headers...');
        const corsResult = await makeRequest(`${FRONTEND_CONFIG.NEXT_PUBLIC_API_ORIGIN}/v1/whoami`, {
            headers: {
                'Origin': FRONTEND_CONFIG.NEXT_PUBLIC_SITE_URL
            }
        });

        const corsHeaders = {
            'access-control-allow-origin': corsResult.headers['access-control-allow-origin'],
            'access-control-allow-credentials': corsResult.headers['access-control-allow-credentials']
        };

        console.log('   CORS Headers:', corsHeaders);

        if (corsHeaders['access-control-allow-origin'] === FRONTEND_CONFIG.NEXT_PUBLIC_SITE_URL) {
            console.log('✅ CORS headers correct');
        } else {
            console.log('❌ CORS headers incorrect');
        }

    } catch (error) {
        console.log('❌ Test error:', error.message);
    }

    console.log('\n' + '='.repeat(50));
    console.log('✅ Frontend API test completed!');
}

// Run the test
testFrontendAPI().catch(console.error);
