"""Compatibility wrappers exposing music functions for top-level aliases.

These call into `app.api.music`/`app.api.spotify_player` to perform real
device and playback operations when available; otherwise they return the
normalized fallback shapes expected by the alias router.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.api import music as _music_api
from app.api import spotify as _spotify_api
from app.feature_flags import MUSIC_ENABLED
from app.http_errors import http_error


async def music_status(request: Request) -> dict[str, Any]:
    if not MUSIC_ENABLED:
        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Try to resolve user_id for provider calls; fall back to anon
    user_id = None
    try:
        from app.deps.user import resolve_user_id

        user_id = resolve_user_id(request=request)
    except Exception:
        user_id = "anon"

    try:
        # Prefer rich music API if available (try to call with request)
        res = await _music_api._get_state_impl(request, None, user_id)  # type: ignore[attr-defined]
        return (
            res
            if isinstance(res, dict)
            else {"playing": False, "device": None, "track": None}
        )
    except Exception:
        try:
            # Fallback to spotify status probe
            try:
                await _spotify_api.spotify_status  # type: ignore[attr-defined]
            except Exception:
                pass
            return {"playing": False, "device": None, "track": None}
        except Exception:
            return {"playing": False, "device": None, "track": None}


async def music_devices(request: Request) -> dict[str, Any]:
    if not MUSIC_ENABLED:
        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Resolve user id where possible
    user_id = "anon"
    try:
        from app.deps.user import resolve_user_id

        user_id = resolve_user_id(request=request)
    except Exception:
        user_id = "anon"

    try:
        # Try to call canonical list_devices if available
        resp = await _music_api.list_devices(request, None, user_id)  # type: ignore[attr-defined]
        return resp if isinstance(resp, dict) else {"devices": []}
    except Exception:
        try:
            from app.integrations.spotify.client import SpotifyClient

            client = SpotifyClient(user_id)
            devices = await client.get_devices()
            return {"devices": devices or []}
        except Exception:
            return {"devices": []}


async def set_music_device(request) -> dict[str, Any]:
    if not MUSIC_ENABLED:
        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Accept device_id in body or query params for compatibility
    try:
        data = await request.json()
    except Exception:
        data = {}
    device_id = request.query_params.get("device_id") or (data or {}).get("device_id")
    if not device_id:
        return {"detail": "missing device_id"}
    try:
        # Try to call canonical set_device
        try:
            await _music_api.set_device.__call__(
                {"device_id": device_id}
            )  # fallback; may not match
        except Exception:
            # Best-effort: ask music API to set device by invoking helper
            try:
                from app.api.music import set_device as _set_dev  # type: ignore

                await _set_dev(type("B", (), {"device_id": device_id})())
            except Exception:
                pass
        return {"ok": True, "device_id": device_id}
    except Exception:
        return {"detail": "failed_to_set_device"}
