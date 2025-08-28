#!/usr/bin/env node

const http = require('http');

async function makeRequest(options, data = null) {
    return new Promise((resolve, reject) => {
        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                resolve({
                    statusCode: res.statusCode,
                    headers: res.headers,
                    body: body
                });
            });
        });

        req.on('error', reject);

        if (data) {
            req.write(data);
        }
        req.end();
    });
}

async function testCompleteFlow() {
    console.log('🎯 Testing Complete Auth Flow After Fix...\n');

    try {
        // Step 1: Test cookie-based login
        console.log('📝 Step 1: Cookie-based login');
        const loginResponse = await makeRequest({
            hostname: 'localhost',
            port: 8000,
            path: '/v1/auth/login?username=qazwsxppo',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': 'AuthFixTester/1.0'
            }
        });

        console.log(`   Login: ${loginResponse.statusCode} ${loginResponse.statusCode === 200 ? '✅' : '❌'}`);

        // Extract cookies
        const setCookieHeaders = loginResponse.headers['set-cookie'] || [];
        const cookies = setCookieHeaders.map(header => {
            const [cookiePart] = header.split(';');
            return cookiePart;
        }).join('; ');

        console.log(`   Cookies set: ${setCookieHeaders.length} cookies`);

        // Step 2: Test whoami with cookies (simulating frontend auth=true)
        console.log('\n🔍 Step 2: Whoami with cookies (auth=true simulation)');
        const whoamiResponse = await makeRequest({
            hostname: 'localhost',
            port: 8000,
            path: '/v1/whoami',
            method: 'GET',
            headers: {
                'Cookie': cookies,
                'Accept': 'application/json',
                'Origin': 'http://localhost:3000',
                'User-Agent': 'AuthFixTester/1.0'
            }
        });

        console.log(`   Whoami: ${whoamiResponse.statusCode} ${whoamiResponse.statusCode === 200 ? '✅' : '❌'}`);

        if (whoamiResponse.statusCode === 200) {
            const whoamiData = JSON.parse(whoamiResponse.body);
            console.log(`   User: ${whoamiData.user_id} (${whoamiData.source})`);
            console.log(`   Authenticated: ${whoamiData.is_authenticated ? '✅' : '❌'}`);
            console.log(`   Session Ready: ${whoamiData.session_ready ? '✅' : '❌'}`);
        }

        // Step 3: Test Spotify status
        console.log('\n🎵 Step 3: Spotify status with cookies');
        const spotifyResponse = await makeRequest({
            hostname: 'localhost',
            port: 8000,
            path: '/v1/spotify/status',
            method: 'GET',
            headers: {
                'Cookie': cookies,
                'Accept': 'application/json',
                'User-Agent': 'AuthFixTester/1.0'
            }
        });

        console.log(`   Spotify: ${spotifyResponse.statusCode} ${spotifyResponse.statusCode === 200 ? '✅' : '❌'}`);

        if (spotifyResponse.statusCode === 200) {
            const spotifyData = JSON.parse(spotifyResponse.body);
            console.log(`   Connected: ${spotifyData.connected ? '✅' : '❌'}`);
        }

        // Step 4: Summary
        console.log('\n🎯 Summary:');
        const loginOk = loginResponse.statusCode === 200;
        const whoamiOk = whoamiResponse.statusCode === 200;
        const spotifyOk = spotifyResponse.statusCode === 200;

        console.log(`   Cookie Login: ${loginOk ? '✅' : '❌'}`);
        console.log(`   Whoami Check: ${whoamiOk ? '✅' : '❌'}`);
        console.log(`   Spotify Status: ${spotifyOk ? '✅' : '❌'}`);

        if (loginOk && whoamiOk && spotifyOk) {
            console.log('\n🎉 ALL TESTS PASSED! The fix should work.');
            console.log('   Next: Refresh your frontend (Ctrl+R) and try logging in');
        } else {
            console.log('\n❌ Some tests failed. Check the logs above.');
        }

    } catch (error) {
        console.error('❌ Test failed:', error.message);
    }
}

testCompleteFlow();
