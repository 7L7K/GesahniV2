#!/usr/bin/env node

// Load environment variables from .env.local
require('dotenv').config({ path: '.env.local' });

const http = require('http');
const https = require('https');

const FRONTEND_URL = 'http://localhost:3000';
const BACKEND_URL = 'http://localhost:8000';

const colors = {
    green: '\x1b[32m',
    red: '\x1b[31m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    reset: '\x1b[0m',
    bold: '\x1b[1m'
};

function log(message, color = 'reset') {
    console.log(`${colors[color]}${message}${colors.reset}`);
}

function makeRequest(url, options = {}) {
    return new Promise((resolve, reject) => {
        const urlObj = new URL(url);
        const client = urlObj.protocol === 'https:' ? https : http;

        const req = client.request(url, {
            method: options.method || 'GET',
            headers: options.headers || {},
            timeout: 5000
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                resolve({
                    status: res.statusCode,
                    headers: res.headers,
                    data: data
                });
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });

        if (options.body) {
            req.write(options.body);
        }
        req.end();
    });
}

async function testFrontendRoutes() {
    log('\n🔍 Testing Frontend Routes...', 'blue');

    const routes = [
        { path: '/', name: 'Home Page' },
        { path: '/login', name: 'Login Page' },
        { path: '/sign-in', name: 'Sign In Page' },
        { path: '/sign-up', name: 'Sign Up Page' },
        { path: '/settings', name: 'Settings Page' },
        { path: '/debug', name: 'Debug Page' },
        { path: '/docs', name: 'Docs Page' }
    ];

    for (const route of routes) {
        try {
            const response = await makeRequest(`${FRONTEND_URL}${route.path}`);
            if (response.status === 200) {
                log(`✅ ${route.name} (${route.path}): ${response.status}`, 'green');
            } else if (response.status === 307) {
                log(`✅ ${route.name} (${route.path}): ${response.status} - Redirect (expected for auth)`, 'green');
            } else if (response.status === 404) {
                log(`⚠️  ${route.name} (${route.path}): ${response.status} - Not Found`, 'yellow');
            } else {
                log(`❌ ${route.name} (${route.path}): ${response.status}`, 'red');
            }
        } catch (error) {
            log(`❌ ${route.name} (${route.path}): Error - ${error.message}`, 'red');
        }
    }
}

async function testBackendHealth() {
    log('\n🔍 Testing Backend Health...', 'blue');

    try {
        const response = await makeRequest(`${BACKEND_URL}/healthz`);
        if (response.status === 200) {
            log(`✅ Backend Health Check: ${response.status}`, 'green');
        } else {
            log(`⚠️  Backend Health Check: ${response.status}`, 'yellow');
        }
    } catch (error) {
        log(`❌ Backend Health Check: Error - ${error.message}`, 'red');
    }
}

async function testAuthenticationEndpoints() {
    log('\n🔍 Testing Authentication Endpoints...', 'blue');

    const authEndpoints = [
        { path: '/v1/whoami', name: 'Whoami Endpoint' },
        { path: '/v1/login', name: 'Login Endpoint' },
        { path: '/v1/register', name: 'Register Endpoint' }
    ];

    for (const endpoint of authEndpoints) {
        try {
            const response = await makeRequest(`${BACKEND_URL}${endpoint.path}`);
            if (response.status === 401) {
                log(`✅ ${endpoint.name}: ${response.status} - Properly protected`, 'green');
            } else if (response.status === 200) {
                log(`⚠️  ${endpoint.name}: ${response.status} - Unexpected success`, 'yellow');
            } else {
                log(`ℹ️  ${endpoint.name}: ${response.status}`, 'blue');
            }
        } catch (error) {
            log(`❌ ${endpoint.name}: Error - ${error.message}`, 'red');
        }
    }
}

async function testCORSConfiguration() {
    log('\n🔍 Testing CORS Configuration...', 'blue');

    try {
        const response = await makeRequest(`${BACKEND_URL}/v1/whoami`, {
            method: 'OPTIONS',
            headers: {
                'Origin': FRONTEND_URL,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Content-Type, Authorization'
            }
        });

        const corsHeaders = response.headers;
        const hasCorsOrigin = corsHeaders['access-control-allow-origin'];
        const hasCorsMethods = corsHeaders['access-control-allow-methods'];
        const hasCorsHeaders = corsHeaders['access-control-allow-headers'];

        if (hasCorsOrigin && hasCorsMethods && hasCorsHeaders) {
            log(`✅ CORS Configuration: Properly configured`, 'green');
            log(`   Origin: ${hasCorsOrigin}`, 'blue');
            log(`   Methods: ${hasCorsMethods}`, 'blue');
            log(`   Headers: ${hasCorsHeaders}`, 'blue');
        } else {
            log(`⚠️  CORS Configuration: Missing headers`, 'yellow');
        }
    } catch (error) {
        log(`❌ CORS Configuration: Error - ${error.message}`, 'red');
    }
}

async function testStaticAssets() {
    log('\n🔍 Testing Static Assets...', 'blue');

    const assets = [
        '/favicon.ico',
        '/apple-touch-icon.png',
        '/_next/static/css/app/layout.css'
    ];

    for (const asset of assets) {
        try {
            const response = await makeRequest(`${FRONTEND_URL}${asset}`);
            if (response.status === 200) {
                log(`✅ Static Asset ${asset}: ${response.status}`, 'green');
            } else {
                log(`⚠️  Static Asset ${asset}: ${response.status}`, 'yellow');
            }
        } catch (error) {
            log(`❌ Static Asset ${asset}: Error - ${error.message}`, 'red');
        }
    }
}

async function testEnvironmentConfiguration() {
    log('\n🔍 Testing Environment Configuration...', 'blue');

    const requiredEnvVars = [
        'NEXT_PUBLIC_API_ORIGIN',
        'NEXT_PUBLIC_SITE_URL',
        'NEXT_PUBLIC_HEADER_AUTH_MODE'
    ];

    const optionalEnvVars = [
        'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY',
        'CLERK_SECRET_KEY'
    ];

    log('Required Environment Variables:', 'blue');
    for (const envVar of requiredEnvVars) {
        const value = process.env[envVar];
        if (value) {
            log(`✅ ${envVar}: Set`, 'green');
        } else {
            log(`❌ ${envVar}: Not set`, 'red');
        }
    }

    log('\nOptional Environment Variables:', 'blue');
    for (const envVar of optionalEnvVars) {
        const value = process.env[envVar];
        if (value) {
            log(`✅ ${envVar}: Set`, 'green');
        } else {
            log(`⚠️  ${envVar}: Not set (optional)`, 'yellow');
        }
    }
}

async function runComprehensiveTest() {
    log(`${colors.bold}🚀 Starting Comprehensive Frontend Test${colors.reset}`, 'blue');
    log(`Frontend URL: ${FRONTEND_URL}`, 'blue');
    log(`Backend URL: ${BACKEND_URL}`, 'blue');

    await testEnvironmentConfiguration();
    await testFrontendRoutes();
    await testBackendHealth();
    await testAuthenticationEndpoints();
    await testCORSConfiguration();
    await testStaticAssets();

    log('\n✨ Comprehensive test completed!', 'green');
}

// Run the test
runComprehensiveTest().catch(error => {
    log(`\n💥 Test failed: ${error.message}`, 'red');
    process.exit(1);
});
