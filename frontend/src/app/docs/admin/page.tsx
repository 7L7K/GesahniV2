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
            <h2>Router decisions</h2>
            <p>
                Inspect recent routing decisions and explanations. Tune <code>router_rules.yaml</code>
                on the backend for deterministic behavior.
            </p>
        </article>
    );
}


