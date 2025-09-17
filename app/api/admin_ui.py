from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from app.deps.scopes import docs_security_with
from app.deps.user import get_current_user_id
from app.status import _admin_token

router = APIRouter(
    tags=["Admin"], dependencies=[Depends(docs_security_with(["admin:write"]))]
)


def _guard(token: str | None) -> None:
    tok = _admin_token()
    if tok and token != tok:
        from app.http_errors import http_error

        raise http_error(
            code="access_forbidden", message="access forbidden", status=403
        )


def _html_page(title: str, body: str) -> str:
    html = """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; margin: 20px; color: #222; }}
    header {{ display:flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
    nav a {{ margin-right: 12px; text-decoration:none; color:#06c; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; }}
    .badge {{ padding:2px 6px; border-radius: 6px; background:#efefef; font-size: 12px; }}
    .ok {{ color: #090; }} .err {{ color: #c00; }}
    code {{ background:#f7f7f7; padding:2px 4px; border-radius:4px; }}
  </style>
  <script>
    async function refreshMetrics() {{
      const res = await fetch('/v1/admin/metrics?token=' + encodeURIComponent(localStorage.getItem('admin_token')||''));
      if (!res.ok) return;
      const data = await res.json();
      const m = data.metrics || {{}};
      document.getElementById('m_llama').innerText = m.llama || 0;
      document.getElementById('m_gpt').innerText = m.gpt || 0;
      document.getElementById('m_fallback').innerText = m.fallback || 0;
      document.getElementById('m_cache').innerText = (data.cache_hit_rate||0).toFixed(2);
    }}
    async function refreshDecisions() {{
      const res = await fetch('/v1/admin/router/decisions?limit=50&token=' + encodeURIComponent(localStorage.getItem('admin_token')||''));
      if (!res.ok) return;
      const data = await res.json();
      const rows = (data.items||[]).slice(0,50).map(it => `
        <tr>
          <td><code>${it.req_id||''}</code></td>
          <td>${it.intent||''}</td>
          <td>${it.engine||''}</td>
          <td>${it.model||''}</td>
          <td>${it.route_reason||''}</td>
          <td>${it.latency_ms||0} ms</td>
        </tr>`).join('');
      document.getElementById('decisions_tbody').innerHTML = rows;
    }}
    function saveToken() {{ const v = document.getElementById('adm_tok').value; localStorage.setItem('admin_token', v); refreshAll(); }}
    function refreshAll() {{ refreshMetrics(); refreshDecisions(); }}
    window.addEventListener('load', ()=>{ refreshAll(); });
  </script>
</head>
<body>
  <header>
    <div><strong>{title}</strong></div>
    <nav>
      <a href='/v1/admin/ui'>Dashboard</a>
      <a href='/v1/admin/ui/retrieval'>Retrieval</a>
      <a href='/v1/admin/ui/config'>Config</a>
    </nav>
  </header>
  {body}
</body>
</html>
"""
    return html.replace("{title}", title).replace("{body}", body)


@router.get("/admin/ui", response_class=HTMLResponse)
def admin_ui_home(
    token: str | None = Query(default=None), user_id: str = Depends(get_current_user_id)
):
    _guard(token)
    from pathlib import Path

    from fastapi import Response

    _ASSETS = Path(__file__).resolve().parents[1] / "admin_ui_assets"
    html = (_ASSETS / "index.html").read_text(encoding="utf-8")
    return Response(content=html, media_type="text/html")


@router.get("/admin/ui/retrieval", response_class=HTMLResponse)
async def admin_ui_retrieval(
    token: str | None = Query(default=None), user_id: str = Depends(get_current_user_id)
):
    _guard(token)
    body = """
    <p>Recent retrieval traces are available via the API. Use the token box on the Dashboard to authorize requests.</p>
    <ul>
      <li><code>/v1/admin/retrieval/last?limit=200</code></li>
      <li><code>/v1/admin/qdrant/collections?names=kb:default</code></li>
    </ul>
    """
    return _html_page("Retrieval", body)


@router.get("/admin/ui/config", response_class=HTMLResponse)
async def admin_ui_config(
    token: str | None = Query(default=None), user_id: str = Depends(get_current_user_id)
):
    _guard(token)
    body = """
    <p>Use <code>/v1/admin/flags</code> to flip runtime flags quickly.</p>
    <ul>
      <li><code>RETRIEVAL_PIPELINE=true</code></li>
      <li><code>RETRIEVE_USE_HOSTED_CE=true</code></li>
      <li><code>DEBUG_MODEL_ROUTING=true</code></li>
    </ul>
    """
    return _html_page("Config", body)


__all__ = ["router"]
