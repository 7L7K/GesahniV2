from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

try:  # Type-only import; tolerate absence during early import
    from app.api.ask_contract import AskRequest  # type: ignore
except Exception:  # pragma: no cover
    AskRequest = Any  # type: ignore


class Hook(Protocol):
    @property
    def name(self) -> str:  # pragma: no cover - simple property
        ...

    async def run(self, result: dict[str, Any], request: AskRequest) -> None: ...


_HOOKS: list[Hook] = []


def register_hook(hook: Hook) -> None:
    _HOOKS.append(hook)


def list_hooks() -> list[Hook]:
    return list(_HOOKS)


async def run_post_hooks(result: dict[str, Any], request: AskRequest) -> dict[str, Any]:
    """Run all registered hooks with supervision and return a summary.

    This function must never raise; it returns a dict summary with per-hook
    results including timing and error messages when applicable.
    """
    hooks = list_hooks()
    if not hooks:
        return {"results": [], "ok": True}

    outcomes: list[dict[str, Any]] = []

    async def _run_one(h: Hook) -> None:
        start = time.monotonic()
        ok = True
        err: str | None = None
        try:
            await h.run(result, request)
        except Exception as e:  # Never leak exceptions
            ok = False
            err = str(e)
        finally:
            dur_ms = int((time.monotonic() - start) * 1000)
            outcomes.append(
                {
                    "name": getattr(h, "name", "hook"),
                    "ok": ok,
                    "error": err,
                    "ms": dur_ms,
                }
            )

    # Prefer TaskGroup when available (py3.11+); otherwise gather
    try:
        from asyncio import TaskGroup  # type: ignore[attr-defined]

        async with TaskGroup() as tg:  # type: ignore
            for h in hooks:
                tg.create_task(_run_one(h))
    except Exception:
        await asyncio.gather(*[_run_one(h) for h in hooks], return_exceptions=True)

    return {"results": outcomes, "ok": all(x.get("ok", False) for x in outcomes)}
