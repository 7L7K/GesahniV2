export default function ProactiveDocs() {
    return (
        <article>
            <h1>Proactive Features</h1>
            <p>
                When enabled, the proactive engine schedules periodic tasks: Home Assistant state
                snapshots, weather updates, calendar refreshes, door‑unlock notifications and
                auto‑lock follow‑ups, and a daily self‑review.
            </p>
            <h2>Curiosity prompts</h2>
            <p>
                If a recent answer was low‑confidence or profile info is missing, the assistant may
                ask a brief follow‑up (e.g., “Quick question: what’s your timezone?”).
            </p>
            <h2>Controls</h2>
            <p>
                These behaviors are gated by environment flags on the backend. See README for
                configuration and scheduling details.
            </p>
        </article>
    );
}


