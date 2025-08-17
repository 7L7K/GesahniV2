export default function GettingStarted() {
    return (
        <article>
            <h1>Getting Started</h1>
            <h2>Prerequisites</h2>
            <ul>
                <li>Backend running (FastAPI on port 8000).</li>
                <li>Frontend running (Next.js on port 3000).</li>
                <li>Set environment variables as described in the project README (API keys, HA token).</li>
            </ul>
            <h2>Login</h2>
            <p>
                Open the app at http://127.0.0.1:3000 and click Login. Enter your credentials. If you
                do not have an account, create one via the backend or seed users per your setup.
            </p>
            <h2>Your first prompt</h2>
            <ol>
                <li>Type a message in the input bar.</li>
                <li>Optionally choose a model override from the selector.</li>
                <li>Press Enter. You will see streaming output.</li>
            </ol>
            <h2>Home Assistant setup</h2>
            <ul>
                <li>Ensure HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN are set on the backend.</li>
                <li>Use the “Teach” skill to add aliases (e.g., “when I say ‘kitchen lights’ use light.kitchen”).</li>
                <li>Try: “turn on kitchen lights”. If ambiguous or risky, the app will ask to confirm.</li>
            </ul>
            <h2>Voice capture & transcription</h2>
            <ol>
                <li>Go to Capture in the header.</li>
                <li>Start a recording; stop to save a session.</li>
                <li>Transcription and tagging run, storing results for search later.</li>
            </ol>
            <h2>Where to next</h2>
            <p>See Chat, Home Assistant, Voice & Sessions, and Skills for deeper usage.</p>
        </article>
    );
}


