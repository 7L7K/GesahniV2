export default function TroubleshootingDocs() {
    return (
        <article>
            <h1>Troubleshooting</h1>
            <h2>Can’t connect</h2>
            <ul>
                <li>Verify backend is running on port 8000 and CORS allows the frontend origin.</li>
                <li>Check <code>/healthz</code> and <code>/status</code> endpoints.</li>
            </ul>
            <h2>Home Assistant errors</h2>
            <ul>
                <li>Confirm <code>HOME_ASSISTANT_TOKEN</code> and that the entity exists.</li>
                <li>If asked to confirm, reply with “confirm” to proceed.</li>
            </ul>
            <h2>Transcription issues</h2>
            <ul>
                <li>Ensure audio format is supported; see capture page hints.</li>
                <li>Check backend logs for Whisper/API errors.</li>
            </ul>
            <h2>Routing surprises</h2>
            <ul>
                <li>Use the Admin router decisions page to see why a model was chosen.</li>
                <li>Override the model in the chat UI for specific prompts.</li>
            </ul>
        </article>
    );
}


