#!/usr/bin/env node
/**
 * Comprehensive diagnostic test for CORS, authentication, and connection issues
 * Run with: node diagnostic_test.js
 */

const https = require('https');
const http = require('http');

const BACKEND_URL = 'http://localhost:8000';
const FRONTEND_URL = 'http://localhost:3000';
const TEST_SERVER_URL = 'http://localhost:8080';

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

async function testBackendHealth() {
    console.log('\n🏥 Testing Backend Health...');

    try {
        const result = await makeRequest(`${BACKEND_URL}/health/live`);
        if (result.status === 200) {
            console.log('✅ Backend is healthy');
        } else {
            console.log(`❌ Backend health check failed: ${result.status}`);
        }
    } catch (error) {
        console.log(`❌ Backend health check error: ${error.message}`);
    }
}

async function testCorsForOrigin(origin) {
    console.log(`\n🌐 Testing CORS for origin: ${origin}`);

    try {
        // Test OPTIONS preflight
        const preflightResult = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
            method: 'OPTIONS',
            headers: {
                'Origin': origin,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Content-Type,Authorization'
            }
        });

        if (preflightResult.status === 200) {
            console.log(`✅ CORS preflight successful for ${origin}`);
            console.log(`   Access-Control-Allow-Origin: ${preflightResult.headers['access-control-allow-origin']}`);
            console.log(`   Access-Control-Allow-Credentials: ${preflightResult.headers['access-control-allow-credentials']}`);
        } else {
            console.log(`❌ CORS preflight failed for ${origin}: ${preflightResult.status}`);
        }

        // Test actual GET request
        const getResult = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
            headers: {
                'Origin': origin,
                'Content-Type': 'application/json'
            }
        });

        if (getResult.status === 200) {
            console.log(`✅ GET request successful for ${origin}`);
            console.log(`   Access-Control-Allow-Origin: ${getResult.headers['access-control-allow-origin']}`);
            console.log(`   Access-Control-Allow-Credentials: ${getResult.headers['access-control-allow-credentials']}`);
        } else {
            console.log(`❌ GET request failed for ${origin}: ${getResult.status}`);
        }

    } catch (error) {
        console.log(`❌ CORS test error for ${origin}: ${error.message}`);
    }
}

async function testAuthenticationFlow() {
    console.log('\n🔐 Testing Authentication Flow...');

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
            console.log(`   Access token length: ${loginResult.data.access_token.length}`);
            console.log(`   Refresh token length: ${loginResult.data.refresh_token?.length || 0}`);

            // Test authenticated request with Bearer token
            const authResult = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
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
                console.log('   Response:', authResult.data);
            }

            // Test cookie authentication
            const cookieResult = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
                headers: {
                    'Cookie': `access_token=${loginResult.data.access_token}`,
                    'Origin': 'http://localhost:3000'
                }
            });

            if (cookieResult.status === 200 && cookieResult.data.is_authenticated) {
                console.log('✅ Cookie authentication successful');
                console.log(`   User: ${cookieResult.data.user.id}`);
                console.log(`   Source: ${cookieResult.data.source}`);
            } else {
                console.log('❌ Cookie authentication failed:', cookieResult.status);
            }

        } else {
            console.log('❌ Login failed:', loginResult.status);
            console.log('   Response:', loginResult.data);
        }
    } catch (error) {
        console.log('❌ Authentication test error:', error.message);
    }
}

async function testFrontendConnection() {
    console.log('\n🌍 Testing Frontend Connection...');

    try {
        const result = await makeRequest(FRONTEND_URL);
        if (result.status === 200) {
            console.log('✅ Frontend is accessible');
        } else {
            console.log(`❌ Frontend connection failed: ${result.status}`);
        }
    } catch (error) {
        console.log(`❌ Frontend connection error: ${error.message}`);
    }
}

async function testTestServerConnection() {
    console.log('\n🧪 Testing Test Server Connection...');

    try {
        const result = await makeRequest(`${TEST_SERVER_URL}/test_frontend_backend_connection.html`);
        if (result.status === 200) {
            console.log('✅ Test server is accessible');
        } else {
            console.log(`❌ Test server connection failed: ${result.status}`);
        }
    } catch (error) {
        console.log(`❌ Test server connection error: ${error.message}`);
    }
}

async function testSpecificEndpoints() {
    console.log('\n🎯 Testing Specific Endpoints...');

    const endpoints = [
        { path: '/v1/whoami', method: 'GET', name: 'Whoami' },
        { path: '/v1/models', method: 'GET', name: 'Models' },
        { path: '/v1/status', method: 'GET', name: 'Status' },
        { path: '/debug/config', method: 'GET', name: 'Debug Config' }
    ];

    for (const endpoint of endpoints) {
        try {
            const result = await makeRequest(`${BACKEND_URL}${endpoint.path}`, {
                method: endpoint.method,
                headers: {
                    'Origin': 'http://localhost:3000'
                }
            });

            if (result.status === 200) {
                console.log(`✅ ${endpoint.name} endpoint working`);
            } else {
                console.log(`❌ ${endpoint.name} endpoint failed: ${result.status}`);
            }
        } catch (error) {
            console.log(`❌ ${endpoint.name} endpoint error: ${error.message}`);
        }
    }
}

async function runDiagnostics() {
    console.log('🔍 Starting Comprehensive Diagnostics');
    console.log('='.repeat(60));

    // Test basic connectivity
    await testBackendHealth();
    await testFrontendConnection();
    await testTestServerConnection();

    // Test CORS for all origins
    for (const origin of TEST_ORIGINS) {
        await testCorsForOrigin(origin);
    }

    // Test authentication
    await testAuthenticationFlow();

    // Test specific endpoints
    await testSpecificEndpoints();

    console.log('\n' + '='.repeat(60));
    console.log('✅ Diagnostics completed!');
    console.log('\n📋 Next Steps:');
    console.log('1. Check browser console for any JavaScript errors');
    console.log('2. Verify the test page at http://localhost:8080/test_frontend_backend_connection.html');
    console.log('3. Test the main frontend at http://localhost:3000');
    console.log('4. Check browser network tab for failed requests');
}

// Run the diagnostics
runDiagnostics().catch(console.error);
