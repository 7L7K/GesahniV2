export default function SecurityDocs() {
    return (
        <article>
            <h1>Security</h1>
            <h2>Authentication</h2>
            <p>
                The backend issues JWT access and refresh tokens. Scopes can be enforced via
                environment flags. Use the Login page to authenticate; tokens are stored securely
                on the client.
            </p>
            <h2>RBAC</h2>
            <p>
                Admin endpoints require the <code>admin</code> scope and an optional
                <code>ADMIN_TOKEN</code>. See the Admin page for protected operations.
            </p>
            <h2>Data handling</h2>
            <ul>
                <li>PII redaction before vector store writes and transcript storage.</li>
                <li>Encrypted backups at rest (AES‑256‑CBC) with key rotation guidance.</li>
                <li>Audit trail for key actions (e.g., service calls, pins).</li>
                <li>Rate limits and moderation guardrails on risky actions.</li>
            </ul>
        </article>
    );
}


