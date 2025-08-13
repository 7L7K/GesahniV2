export default function AdminDocs() {
    return (
        <article>
            <h1>Admin</h1>
            <p>
                Admin pages expose metrics and router decisions when authorized. Use them to
                understand routing, cache behavior, and system health.
            </p>
            <h2>Metrics</h2>
            <p>See request volume, latency, cache hit rate, and cost metrics.</p>
            <ul>
                <li><code>dependency_latency_seconds</code> (dependency, operation)</li>
                <li><code>embedding_latency_seconds</code> (backend)</li>
                <li><code>vector_op_latency_seconds</code> (operation)</li>
                <li><code>model_latency_seconds</code> (model)</li>
                <li><code>rate_limit_allow_total</code> / <code>rate_limit_block_total</code></li>
            </ul>
            <p>
                Prometheus metrics are exposed by the backend at <code>/metrics</code> when
                <code>PROMETHEUS_ENABLED=1</code>. Import the provided Grafana dashboard file
                (<code>grafana_dashboard.json</code>) to visualize latency percentiles, cost, cache hit
                rate, vector operations, and dependency timing.
            </p>
            <h2>Router decisions</h2>
            <p>
                Inspect recent routing decisions and explanations. Tune <code>router_rules.yaml</code>
                on the backend for deterministic behavior.
            </p>
            <h2>Load testing & SLOs</h2>
            <p>
                Use the included scripts to validate performance:
            </p>
            <ul>
                <li>k6: <code>k6 run scripts/k6_load_test.js -e BASE_URL=http://localhost:8000</code></li>
                <li>Locust: <code>locust -f locustfile.py --host=http://localhost:8000</code></li>
            </ul>
            <p>
                Default SLOs (k6 thresholds): p95 &lt; 500ms, &lt;1% error rate. Adjust to fit your deployment.
            </p>
        </article>
    );
}


