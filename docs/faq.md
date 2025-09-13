## Why not just "turn on CORS everywhere"?

Because credentials + wildcards don’t mix, browsers dislike third‑party cookies (Safari blocks them; Chrome is deprecating them), and “localhost vs 127.0.0.1” becomes a silent cross-site split. Same-origin dev avoids all of that.

