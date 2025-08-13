import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
    thresholds: {
        // Global SLOs
        http_req_failed: ['rate<0.01'], // <1% errors
        http_req_duration: ['p(95)<500'], // p95 < 500ms
    },
    scenarios: {
        smoke: {
            executor: 'constant-vus',
            vus: 5,
            duration: '1m',
        },
    },
};

const BASE = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
    // Health
    let res = http.get(`${BASE}/healthz`);
    check(res, { 'health 200': (r) => r.status === 200 });

    // Me (anon)
    res = http.get(`${BASE}/v1/me`);
    check(res, { 'me 200': (r) => r.status === 200 });

    // Ask minimal
    res = http.post(`${BASE}/v1/ask`, JSON.stringify({ prompt: 'hello' }), {
        headers: { 'Content-Type': 'application/json' },
    });
    check(res, { 'ask status okish': (r) => [200, 400, 401, 500].includes(r.status) });

    sleep(1);
}


