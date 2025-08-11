export default function FAQDocs() {
    return (
        <article>
            <h1>FAQ</h1>
            <h2>Can I force LLaMA or GPT?</h2>
            <p>Yes. Use the model selector in the chat UI or pass a model override to the API.</p>
            <h2>Does it work offline?</h2>
            <p>
                Local LLaMA replies can work offline. Cloud features (GPT, Whisper, search) require
                connectivity and API keys.
            </p>
            <h2>How is my data protected?</h2>
            <p>
                Transcripts and memory undergo PII redaction before storage. Backups are encrypted.
                Admin endpoints require RBAC.
            </p>
        </article>
    );
}


