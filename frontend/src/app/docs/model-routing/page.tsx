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
        </article>
    );
}


