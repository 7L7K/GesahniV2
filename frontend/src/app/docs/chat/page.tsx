export default function ChatDocs() {
    return (
        <article>
            <h1>Chat</h1>
            <p>
                The chat bar accepts freeform prompts. The system routes to LLaMA for quick
                responses and escalates to GPT for complex queries. You can override the model
                if needed using the model selector.
            </p>
            <h2>Tips</h2>
            <ul>
                <li>Ask concise questions for faster local replies.</li>
                <li>For research, code, or long analysis, the router may choose GPT‑4o.</li>
                <li>Repeat questions may hit the semantic cache and return instantly.</li>
            </ul>
            <h2>Streaming</h2>
            <p>Responses stream token‑by‑token. Cancel anytime and refine your prompt.</p>
            <h2>Provenance</h2>
            <p>
                When memory influenced a reply, lines may include tags like [#chunk:abcd1234],
                indicating which stored memory chunk the answer referenced.
            </p>
        </article>
    );
}


