export default function MemoryDocs() {
    return (
        <article>
            <h1>Memory & Retrieval</h1>
            <p>
                The system stores selective chunks from transcripts and notes. During answering, it
                retrieves relevant memories and may tag lines in the response with provenance
                markers like [#chunk:XXXX]. A semantic cache can instantly answer repeated prompts.
            </p>
            <h2>Controlling memory</h2>
            <ul>
                <li>Manage user notes in the UI or via API.</li>
                <li>Invalidate cached answers using the CLI tool described in the README.</li>
            </ul>
            <h2>Backend options</h2>
            <p>Default store is Chroma. You can switch to in-memory for tests.</p>
            <ul>
                <li><code>VECTOR_STORE</code>: <code>memory</code> | <code>chroma</code> | <code>qdrant</code> | <code>dual</code> | <code>cloud</code></li>
                <li><code>STRICT_VECTOR_STORE</code>: fail hard on init errors when set</li>
            </ul>
            <h3>Observability</h3>
            <ul>
                <li><code>embedding_latency_seconds</code> (openai|llama|stub)</li>
                <li><code>vector_op_latency_seconds</code> (upsert|search|scroll|delete)</li>
                <li><code>dependency_latency_seconds</code> (qdrant operations timing)</li>
            </ul>
        </article>
    );
}
