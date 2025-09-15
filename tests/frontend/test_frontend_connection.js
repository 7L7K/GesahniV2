#!/usr/bin/env node
/**
 * Test script to verify frontend-backend connection
 * Run with: node test_frontend_connection.js
 */

const https = require('https');
const http = require('http');

const BACKEND_URL = 'http://localhost:8000';
const TEST_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:8080',
    'http://10.0.0.138:3000'
];

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

async function testCorsPreflight(origin) {
    console.log(`\n🔍 Testing CORS preflight for origin: ${origin}`);

    try {
        const result = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
            method: 'OPTIONS',
            headers: {
                'Origin': origin,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Content-Type,Authorization'
            }
        });

        if (result.status === 200) {
            console.log(`✅ CORS preflight successful for ${origin}`);
            console.log(`   Access-Control-Allow-Origin: ${result.headers['access-control-allow-origin']}`);
            console.log(`   Access-Control-Allow-Credentials: ${result.headers['access-control-allow-credentials']}`);
        } else {
            console.log(`❌ CORS preflight failed for ${origin}: ${result.status}`);
        }
    } catch (error) {
        console.log(`❌ CORS preflight error for ${origin}: ${error.message}`);
    }
}

async function testAuthentication() {
    console.log('\n🔐 Testing authentication flow...');

    try {
        // Test login
        const loginResult = await makeRequest(`${BACKEND_URL}/v1/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Origin': 'http://localhost:3000'
            },
            body: JSON.stringify({
                username: 'testuser',
                password: 'testpass123'
            })
        });

        if (loginResult.status === 200 && loginResult.data.access_token) {
            console.log('✅ Login successful');

            // Test authenticated request
            const authResult = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${loginResult.data.access_token}`,
                    'Origin': 'http://localhost:3000'
                }
            });

            if (authResult.status === 200 && authResult.data.is_authenticated) {
                console.log('✅ Authenticated request successful');
                console.log(`   User: ${authResult.data.user.id}`);
                console.log(`   Source: ${authResult.data.source}`);
            } else {
                console.log('❌ Authenticated request failed:', authResult.status);
            }
        } else {
            console.log('❌ Login failed:', loginResult.status);
        }
    } catch (error) {
        console.log('❌ Authentication test error:', error.message);
    }
}

async function testWhoami() {
    console.log('\n👤 Testing /whoami endpoint...');

    try {
        const result = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
            headers: {
                'Origin': 'http://localhost:3000'
            }
        });

        if (result.status === 200) {
            console.log('✅ /whoami endpoint accessible');
            console.log(`   Authenticated: ${result.data.is_authenticated}`);
            console.log(`   Session Ready: ${result.data.session_ready}`);
        } else {
            console.log('❌ /whoami endpoint failed:', result.status);
        }
    } catch (error) {
        console.log('❌ /whoami test error:', error.message);
    }
}

async function runTests() {
    console.log('🚀 Starting Frontend-Backend Connection Tests');
    console.log('='.repeat(50));

    // Test CORS for all origins
    for (const origin of TEST_ORIGINS) {
        await testCorsPreflight(origin);
    }

    // Test basic endpoint
    await testWhoami();

    // Test authentication
    await testAuthentication();

    console.log('\n' + '='.repeat(50));
    console.log('✅ All tests completed!');
}

// Run the tests
runTests().catch(console.error);
