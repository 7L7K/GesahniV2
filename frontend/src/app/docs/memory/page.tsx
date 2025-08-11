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
        </article>
    );
}


