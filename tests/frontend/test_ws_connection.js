// Test WebSocket connection to music endpoint
const WebSocket = require('ws');

console.log('Testing WebSocket connection to ws://localhost:8000/v1/ws/music');

const ws = new WebSocket('ws://localhost:8000/v1/ws/music', ['json.realtime.v1']);

ws.on('open', function open() {
    console.log('WebSocket connection opened');
});

ws.on('message', function message(data) {
    console.log('Received:', data.toString());
});

ws.on('error', function error(err) {
    console.error('WebSocket error:', err.message);
});

ws.on('close', function close(code, reason) {
    console.log('WebSocket closed:', code, reason.toString());
});

setTimeout(() => {
    console.log('Closing test connection...');
    ws.close();
}, 5000);
