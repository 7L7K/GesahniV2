export default function SkillsDocs() {
    return (
        <article>
            <h1>Skills</h1>
            <p>
                Built‑in skills run before calling any LLM. The first matching skill handles the
                prompt. Examples include Smalltalk, Weather/Forecast, Clock/World Clock, Math,
                Unit and Currency conversion, Calendar, Reminders/Timers, Dictionary, Search,
                Translate, Recipes, Notes, Status, Music, Roku, Climate, Vacuum, and Home
                Assistant device controls.
            </p>
            <h2>How matching works</h2>
            <ul>
                <li>Intent detection uses heuristics plus a semantic model.</li>
                <li>Each skill defines regex patterns; the first match returns a response.</li>
                <li>For greetings, Smalltalk takes precedence.</li>
            </ul>
            <h2>Examples</h2>
            <ul>
                <li>"what’s the weather tomorrow"</li>
                <li>"convert 3 miles to km"</li>
                <li>"set a reminder for 5pm to water plants"</li>
                <li>"translate ‘good morning’ to spanish"</li>
            </ul>
        </article>
    );
}
