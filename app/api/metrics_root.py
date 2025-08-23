import os

from fastapi import APIRouter

router = APIRouter(tags=["Admin"])

if os.getenv("PROMETHEUS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}:
    try:
        from fastapi import Response as _Resp
        from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

        try:
            LLAMA_QUEUE_DEPTH = Gauge("gesahni_llama_queue_depth", "Current LLaMA queue depth")  # noqa: N806
        except Exception:
            class _G:
                def set(self, *_a, **_k): return None
            LLAMA_QUEUE_DEPTH = _G()  # type: ignore

        @router.get("/metrics", include_in_schema=False)
        async def _metrics_route() -> _Resp:  # type: ignore[valid-type]
            try:
                from app.llama_integration import QUEUE_DEPTH as _QD  # type: ignore[attr-defined]
                try:
                    LLAMA_QUEUE_DEPTH.set(int(_QD))  # type: ignore[arg-type]
                except Exception:
                    LLAMA_QUEUE_DEPTH.set(0)  # type: ignore[attr-defined]
            except Exception:
                try:
                    LLAMA_QUEUE_DEPTH.set(0)  # type: ignore[attr-defined]
                except Exception:
                    pass
            data = generate_latest()
            return _Resp(content=data, media_type=CONTENT_TYPE_LATEST)
    except Exception:
        from fastapi import Response as _Resp  # type: ignore

        @router.get("/metrics", include_in_schema=False)
        async def _metrics_route_fallback() -> _Resp:  # type: ignore[valid-type]
            try:
                from app import metrics as _m  # type: ignore
                parts = [
                    f"{_m.REQUEST_COUNT.name} {_m.REQUEST_COUNT.value}",
                    f"{_m.REQUEST_LATENCY.name} {_m.REQUEST_LATENCY.value}",
                ]
                body = ("\n".join(parts) + "\n").encode()
            except Exception:
                body = b""
            return _Resp(content=body, media_type="text/plain; version=0.0.4")
