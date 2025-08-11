export default function HomeAssistantDocs() {
    return (
        <article>
            <h1>Home Assistant</h1>
            <p>
                Gesahni integrates with Home Assistant (HA) to control devices using natural
                language. Ensure the backend has <code>HOME_ASSISTANT_URL</code> and
                <code>HOME_ASSISTANT_TOKEN</code> configured.
            </p>
            <h2>Common commands</h2>
            <ul>
                <li>"turn on kitchen lights" / "turn off bedroom lamp"</li>
                <li>"toggle living room lights"</li>
                <li>"set hallway lights brightness 60"</li>
                <li>"lock front door" / "unlock back door" (unlock requires confirmation)</li>
            </ul>
            <h2>Entity resolution</h2>
            <ul>
                <li>Aliases you teach (e.g., "when I say ‘desk lamp’ use light.desk").</li>
                <li>Exact matches on <code>entity_id</code> or <code>friendly_name</code>.</li>
                <li>Room synonyms (e.g., lounge → living room) and substring fallback.</li>
                <li>Fuzzy match with confidence; low confidence prompts confirmation.</li>
            </ul>
            <h2>Risky actions and confirmation</h2>
            <p>
                Unlocking doors and similar actions require explicit confirmation unless the
                backend is configured to bypass. The assistant will ask you to confirm before
                proceeding.
            </p>
            <h2>Aliases</h2>
            <p>
                You can manage aliases in the UI or via API endpoints under <code>/ha/aliases</code>.
                Aliases make everyday phrases resolve to exact entities.
            </p>
        </article>
    );
}


