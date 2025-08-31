// Test script to reproduce the Google connect issue
console.log('Testing Google Connect API...');

async function testGoogleConnect() {
    try {
        const response = await fetch('http://localhost:8000/v1/google/connect?next=%2Fsettings%23google%3Dconnected', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            credentials: 'include',
        });

        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));

        if (response.ok) {
            const data = await response.json();
            console.log('Response data:', data);
            return data;
        } else {
            const errorText = await response.text();
            console.error('Error response:', errorText);
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

testGoogleConnect()
    .then(result => {
        console.log('Test completed successfully:', result);
    })
    .catch(error => {
        console.error('Test failed:', error);
    });
