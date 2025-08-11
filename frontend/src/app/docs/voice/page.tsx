export default function VoiceDocs() {
    return (
        <article>
            <h1>Voice & Sessions</h1>
            <h2>Capture</h2>
            <ol>
                <li>Open Capture from the header.</li>
                <li>Choose input device and start recording.</li>
                <li>Stop to save a session and generate a session ID.</li>
            </ol>
            <h2>Transcription</h2>
            <p>
                The backend transcribes audio with Whisper and stores the transcript. It extracts
                tags, splits long text, and adds salient chunks into memory for future recall.
            </p>
            <h2>Search</h2>
            <p>
                Use the search UI or API to find sessions by text or tags. Results include snippets
                and recency ranking.
            </p>
            <h2>Tips</h2>
            <ul>
                <li>Keep recordings focused for better tagging and recall.</li>
                <li>Add manual tags to improve later search.</li>
            </ul>
        </article>
    );
}


