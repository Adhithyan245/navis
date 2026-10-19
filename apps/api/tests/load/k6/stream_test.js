import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    vus: 100, // 100 concurrent streams
    duration: '30s',
};

export default function () {
    // Override with K6_API_BASE_URL env var if pointing at a different host
    const base = __ENV.K6_API_BASE_URL || 'http://localhost:8100';
    const url = `${base}/interact`;
    const payload = JSON.stringify({
        query: 'Explore Paris',
        context: {}
    });

    const params = {
        headers: {
            'Content-Type': 'application/json',
        },
        timeout: '120s', // Streaming can take a while
    };

    const res = http.post(url, payload, params);

    // NDJSON should return 200 OK
    check(res, {
        'is status 200': (r) => r.status === 200,
        'has ndjson chunks': (r) => r.body && r.body.includes('event'),
    });
    
    // Simulate frontend processing time/slow consumer behavior
    sleep(1);
}
