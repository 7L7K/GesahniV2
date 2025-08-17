// Test script to debug authentication flow
const fetch = require('node-fetch');

async function testAuthFlow() {
    console.log('Testing authentication flow...');

    // Step 1: Test whoami without auth
    console.log('\n1. Testing /v1/whoami without authentication:');
    try {
        const whoamiRes = await fetch('http://127.0.0.1:8000/v1/whoami');
        const whoamiData = await whoamiRes.json();
        console.log('Status:', whoamiRes.status);
        console.log('Response:', JSON.stringify(whoamiData, null, 2));
    } catch (error) {
        console.error('Error:', error.message);
    }

    // Step 2: Test login
    console.log('\n2. Testing login:');
    try {
        const loginRes = await fetch('http://127.0.0.1:8000/v1/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: 'demo', password: 'secret123' })
        });
        const loginData = await loginRes.json();
        console.log('Status:', loginRes.status);
        console.log('Response:', JSON.stringify(loginData, null, 2));

        if (loginRes.ok && loginData.access_token) {
            // Step 3: Test whoami with token
            console.log('\n3. Testing /v1/whoami with Authorization header:');
            const authRes = await fetch('http://127.0.0.1:8000/v1/whoami', {
                headers: { 'Authorization': `Bearer ${loginData.access_token}` }
            });
            const authData = await authRes.json();
            console.log('Status:', authRes.status);
            console.log('Response:', JSON.stringify(authData, null, 2));

            // Step 4: Test state endpoint with token
            console.log('\n4. Testing /v1/state with Authorization header:');
            const stateRes = await fetch('http://127.0.0.1:8000/v1/state', {
                headers: { 'Authorization': `Bearer ${loginData.access_token}` }
            });
            console.log('Status:', stateRes.status);
            if (stateRes.ok) {
                const stateData = await stateRes.json();
                console.log('Response:', JSON.stringify(stateData, null, 2));
            } else {
                console.log('Error response:', await stateRes.text());
            }
        }
    } catch (error) {
        console.error('Error:', error.message);
    }
}

testAuthFlow().catch(console.error);
