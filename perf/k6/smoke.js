import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || '1m',
  thresholds: {
    http_req_failed: ['rate<0.01'],           // <1% errors
    http_req_duration: ['p(95)<500'],         // p95 < 500ms
  },
};

const BASE = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  let res = http.get(`${BASE}/v1/healthz`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has X-Request-ID': (r) => !!r.headers['X-Request-ID'],
  });
  sleep(1);
}


