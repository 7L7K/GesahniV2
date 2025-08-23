# app/middleware/audit_mw.py
import importlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import req_id_var


class AuditMiddleware(BaseHTTPMiddleware):
    """Append-only audit middleware for HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        resp: Response | None = None
        try:
            resp = await call_next(request)
            return resp
        finally:
            try:
                scopes = getattr(request.state, "scopes", []) or []
                uid = getattr(request.state, "user_id", None)
                req_id = req_id_var.get()
                ip = request.client.host if request.client else None
                route_name = getattr(
                    request.scope.get("endpoint"), "__name__", request.url.path
                )
                status = getattr(resp, "status_code", 500) if resp else 500

                # Prefer new audit API (`app.audit_new.store.append` + AuditEvent)
                try:
                    models = importlib.import_module("app.audit_new.models")
                    store = importlib.import_module("app.audit_new.store")
                    AuditEvent = models.AuditEvent
                    print(
                        f"AUDIT_MW: Using new audit system - models: {models}, store: {store}"
                    )

                    event = AuditEvent(
                        user_id=uid,
                        route=route_name,
                        method=request.method,
                        status=status,
                        ip=ip,
                        req_id=req_id,
                        scopes=(
                            list(scopes)
                            if isinstance(scopes, (list, set, tuple))
                            else []
                        ),
                        action="http_request",
                        meta={"path": request.url.path},
                    )

                    print(f"AUDIT_MW: Created event: {event}")
                    print(f"AUDIT_MW: Event JSON: {event.model_dump_json()}")

                    # Append via the new store API
                    if hasattr(store, "append"):
                        print("AUDIT_MW: Calling store.append")
                        store.append(event)
                        print("AUDIT_MW: store.append completed")
                    else:
                        # Fall back to legacy append_audit if needed
                        legacy = importlib.import_module("app.audit")
                        if hasattr(legacy, "append_audit"):
                            legacy.append_audit(
                                action="http_request",
                                user_id_hashed=uid,
                                data={
                                    "route": route_name,
                                    "method": request.method,
                                    "status": status,
                                    "path": request.url.path,
                                    "scopes": (
                                        list(scopes)
                                        if isinstance(scopes, (list, set, tuple))
                                        else []
                                    ),
                                },
                                ip_address=ip,
                                request_id=req_id,
                            )
                except Exception as e:
                    print(f"AUDIT_MW: New audit system failed: {e}")
                    # As a final fallback, call legacy append_audit if present
                    try:
                        legacy = importlib.import_module("app.audit")
                        if hasattr(legacy, "append_audit"):
                            print("AUDIT_MW: Using legacy audit system")
                            legacy.append_audit(
                                action="http_request",
                                user_id_hashed=uid,
                                data={
                                    "route": route_name,
                                    "method": request.method,
                                    "status": status,
                                    "path": request.url.path,
                                    "scopes": (
                                        list(scopes)
                                        if isinstance(scopes, (list, set, tuple))
                                        else []
                                    ),
                                },
                                ip_address=ip,
                                request_id=req_id,
                            )
                    except Exception:
                        pass
            except Exception:
                # never fail the request due to audit issues
                pass
