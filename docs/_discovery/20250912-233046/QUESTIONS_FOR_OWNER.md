# Questions for Owner

- What are the exact production domains? (Vercel app and Render API) Needed for CORS allowlist, cookies (APP_DOMAIN), and OAuth callbacks.
- Should frontend and backend share a parent domain (e.g., app.example.com and api.example.com)? If yes, confirm `APP_DOMAIN=.example.com` policy for cookies.
- Will uploads/sessions remain on local disk or be moved to object storage? If local, can we provision persistent disk on Render (size/growth expectations)?
- Expected WS usage and traffic? Which endpoints must support WS in prod (e.g., music/care)? Any concurrency expectations for Render instance sizing?
- OAuth providers beyond Google in scope? Any consent screen scopes and redirect URIs to add for preview/prod?
- What vendor backends are mandatory for GA (OpenAI, Ollama, Home Assistant, Qdrant, Redis)? Provide service URLs/credentials, and any network allowlists.
- Any additional headers or proxies in front of Render (e.g., Cloudflare)? If so, confirm `X-Forwarded-Proto` and real IP forwarding for CSRF and logging.
- SLA/health check targets: which endpoints should Render health checks use? (/healthz/ready suggested). Any custom 5xx retry policies?
