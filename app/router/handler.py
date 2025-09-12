from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.api.ask_contract import AskRequest, AskResponse, AskStreamEvent

from . import entrypoint as router_entrypoint


def _shape_usage(raw: dict[str, Any]) -> dict[str, int]:
    usage = raw.get("usage") or {}
    ti = usage.get("tokens_in", usage.get("input_tokens", 0))
    to = usage.get("tokens_out", usage.get("output_tokens", 0))
    return {"tokens_in": int(ti or 0), "tokens_out": int(to or 0)}


def _shape_vendor(raw: dict[str, Any]) -> str:
    return raw.get("vendor") or raw.get("backend") or raw.get("chosen_vendor") or "dryrun"


def _shape_model(raw: dict[str, Any], fallback: str | None) -> str:
    return raw.get("model") or raw.get("chosen_model") or (fallback or "unknown")


def _shape_answer(raw: dict[str, Any]) -> str:
    if isinstance(raw.get("answer"), str):
        return raw["answer"]
    for key in ("text", "message", "echo"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _shape_cache_hit(raw: dict[str, Any]) -> bool:
    v = raw.get("cache_hit")
    if isinstance(v, bool):
        return v
    return bool(raw.get("semantic_cache_hit", False))


def _shape_observability(raw: dict[str, Any]) -> dict[str, Any]:
    obs = raw.get("observability")
    if isinstance(obs, dict):
        return obs
    return {
        "route_decision": raw.get("route") or raw.get("picker_reason"),
        "cb_state": {
            "global_open": raw.get("cb_global_open"),
            "user_open": raw.get("cb_user_open"),
        },
        "fallback_count": raw.get("fallback_count", 0),
        "hooks": raw.get("hooks", {}),
        "timings": raw.get("timings", {}),
    }


async def _call_route_prompt(req: AskRequest) -> dict[str, Any]:
    return await router_entrypoint.route_prompt(req)


async def handle_ask(
    request: AskRequest, *, streaming: bool = False
) -> AskResponse | AsyncIterator[AskStreamEvent]:
    if not streaming:
        raw = await _call_route_prompt(request)
        obs = _shape_observability(raw)
        try:
            hooks_summary = await router_entrypoint.run_post_hooks(raw, request)  # type: ignore[attr-defined]
        except Exception:
            hooks_summary = {"results": [], "ok": True}
        obs["hooks"] = hooks_summary
        # Augment observability with route decision summary
        rd = obs.get("route_decision") if isinstance(obs.get("route_decision"), dict) else {}
        rd.update({
            "skill_won": (rd.get("skill_won") if isinstance(rd, dict) else None),
            "intent": request.intent_hint or "",
            "model": _shape_model(raw, request.model_override),
            "vendor": _shape_vendor(raw),
            "cache_hit": _shape_cache_hit(raw),
        })
        obs["route_decision"] = rd

        # Default timings present for observability
        obs.setdefault("timings", {"route_ms": 0, "vendor_ms": 0, "total_ms": 0})

        resp = AskResponse(
            answer=_shape_answer(raw),
            usage=_shape_usage(raw),
            vendor=_shape_vendor(raw),
            model=_shape_model(raw, request.model_override),
            cache_hit=_shape_cache_hit(raw),
            observability=obs,
        )
        return resp

    async def _stream() -> AsyncIterator[AskStreamEvent]:
        done: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

        async def _worker():
            try:
                raw = await _call_route_prompt(request)
                done.set_result(raw)
            except Exception as e:
                if not done.done():
                    done.set_exception(e)

        task = asyncio.create_task(_worker())

        try:
            while not done.done():
                yield AskStreamEvent(type="ping", data={"ts": datetime.now(UTC).isoformat()})
                await asyncio.sleep(1.0)

            raw = await done
            obs = _shape_observability(raw)
            try:
                hooks_summary = await router_entrypoint.run_post_hooks(raw, request)  # type: ignore[attr-defined]
            except Exception:
                hooks_summary = {"results": [], "ok": True}
            obs["hooks"] = hooks_summary
            rd = obs.get("route_decision") if isinstance(obs.get("route_decision"), dict) else {}
            rd.update({
                "skill_won": (rd.get("skill_won") if isinstance(rd, dict) else None),
                "intent": request.intent_hint or "",
                "model": _shape_model(raw, request.model_override),
                "vendor": _shape_vendor(raw),
                "cache_hit": _shape_cache_hit(raw),
            })
            obs["route_decision"] = rd
            obs.setdefault("timings", {"route_ms": 0, "vendor_ms": 0, "total_ms": 0})

            final = AskResponse(
                answer=_shape_answer(raw),
                usage=_shape_usage(raw),
                vendor=_shape_vendor(raw),
                model=_shape_model(raw, request.model_override),
                cache_hit=_shape_cache_hit(raw),
                observability=obs,
            )
            yield AskStreamEvent(type="final", data=final.model_dump())
        except Exception as e:
            yield AskStreamEvent(type="error", data={"message": str(e)})
        finally:
            task.cancel()
            with contextlib.suppress(Exception):
                await task

    import contextlib  # local import

    return _stream()
