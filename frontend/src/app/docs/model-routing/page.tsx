export default function RoutingDocs() {
    return (
        <article>
            <h1>Model Routing</h1>
            <p>
                The assistant routes prompts deterministically using token length, detected intent,
                presence of retrieval context, and attachments. Short/simple prompts use local LLaMA.
                Long/complex or research/code prompts use GPT (e.g., GPT‑4o). Failures fall back
                between engines.
            </p>
            <h2>Overrides</h2>
            <p>Use the model selector to force a specific model when needed.</p>
            <h2>Budgets & retries</h2>
            <p>Limits prevent runaway costs and retries; heavy tasks escalate only when justified.</p>
            <h2>Observability</h2>
            <p>Routing decisions are recorded for admin review and tuning.</p>
            <ul>
                <li>Prometheus: <code>router_decision_total</code></li>
                <li>Latency histograms per model: <code>model_latency_seconds</code></li>
                <li>Trace headers: <code>X-Request-ID</code> and <code>X-Trace-ID</code></li>
            </ul>
        </article>
    );
}


