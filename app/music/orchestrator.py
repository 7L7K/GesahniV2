from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Iterable, Tuple
from dataclasses import dataclass
from .providers.base import MusicProvider, Device, Track, PlaybackState
from . import policy

logger = logging.getLogger(__name__)


"""
Use provider interface from app.music.providers.base.MusicProvider.
Removed a conflicting local Protocol that had mismatched method signatures.
"""


@dataclass
class OrchestratorState:
    active_provider: str | None = None
    active_device: str | None = None


class MusicOrchestrator:
    def __init__(self, providers: Iterable[MusicProvider]):
        self.providers = {p.name: p for p in providers}
        self.state = OrchestratorState()

    def _provider_for(self, hint: str | None = None) -> MusicProvider | None:
        if hint and hint in self.providers:
            return self.providers[hint]
        # prefer spotify
        for choice in ("spotify", "librespot", "ha"):
            if choice in self.providers:
                return self.providers[choice]
        return next(iter(self.providers.values()), None)

    async def play(self, utterance: str | None = None, *, entity=None, room: str | None = None, vibe: str | None = None, provider_hint: str | None = None) -> dict:
        provider = self._provider_for(provider_hint)
        if not provider:
            raise RuntimeError("No provider available")

        # If caller provided an utterance but no entity, attempt search+disambiguation
        if not entity and utterance:
            hits = await self.search(utterance)
            # Normalize hits into candidates list
            candidates: list[dict] = []
            for t in (hits.get("track") or []):
                candidates.append({"type": "track", "id": t.id if hasattr(t, "id") else t.get("id"), "label": getattr(t, "title", None) or t.get("name")})
            for a in (hits.get("album") or []):
                candidates.append({"type": "album", "id": a.id if hasattr(a, "id") else a.get("id"), "label": getattr(a, "title", None) or a.get("name")})
            for p in (hits.get("playlist") or []):
                candidates.append({"type": "playlist", "id": p.id if hasattr(p, "id") else p.get("id"), "label": getattr(p, "name", None) or p.get("name")})
            # If zero, fallback to provider play with utterance as query (best-effort)
            if not candidates:
                # best-effort: try direct play with utterance as search query
                device_id = await self.device_select(room)
                await provider.play(utterance, "search", device_id=device_id)
                self.state.active_provider = provider.name
                self.state.active_device = device_id
                return {"provider": provider.name, "device": device_id}
            # If exactly one candidate, choose it
            if len(candidates) == 1:
                chosen = candidates[0]
            else:
                # return disambiguation payload
                return {"action": "disambiguate", "candidates": candidates}
            # build entity from chosen
            entity = {"id": chosen["id"], "type": chosen["type"]}

        # device selection
        device_id = await self.device_select(room)
        await provider.play(entity["id"] if entity else "", entity["type"] if entity else "track", device_id=device_id)
        self.state.active_provider = provider.name
        self.state.active_device = device_id
        return {"provider": provider.name, "device": device_id}

    async def seek(self, position_ms: int) -> None:
        p = self._provider_for(self.state.active_provider)
        if p and hasattr(p, "seek"):
            await p.seek(position_ms)

    async def recommend_more_like(self, seed_track_id: str | None = None, limit: int = 10) -> list[dict]:
        p = self._provider_for(self.state.active_provider)
        if not p or not hasattr(p, "recommendations"):
            return []
        seeds = {"tracks": [seed_track_id]} if seed_track_id else {}
        recs = await p.recommendations(seeds, {"limit": limit})
        # normalize to minimal dicts
        out = []
        for t in recs:
            out.append({"id": t.get("id"), "name": t.get("name"), "artists": ", ".join([a.get("name", "") for a in t.get("artists", [])])})
        return out

    async def pause(self) -> None:
        p = self._provider_for(self.state.active_provider)
        if p:
            await p.pause()

    async def resume(self) -> None:
        p = self._provider_for(self.state.active_provider)
        if p:
            await p.resume()

    async def next(self) -> None:
        p = self._provider_for(self.state.active_provider)
        if p:
            await p.next()

    async def previous(self) -> None:
        p = self._provider_for(self.state.active_provider)
        if p:
            await p.previous()

    async def set_volume(self, level: int, *, duck: bool = False, timeout_s: int = 8) -> None:
        p = self._provider_for(self.state.active_provider)
        if p:
            await p.set_volume(level)

    async def search(self, term: str, types: Tuple[str, ...] = ("track", "artist", "album", "playlist")) -> dict:
        p = self._provider_for()
        if not p:
            return {}
        return await p.search(term, types)

    async def list_devices(self) -> list[dict]:
        """Return provider devices in a stable dict shape.

        Keys match common fields used by the UI: id, name, type, volume_percent, is_active.
        """
        p = self._provider_for()
        if not p or not hasattr(p, "list_devices"):
            return []
        items = []
        for d in await p.list_devices():
            items.append(
                {
                    "id": getattr(d, "id", None),
                    "name": getattr(d, "name", None),
                    "type": getattr(d, "type", None),
                    "volume_percent": getattr(d, "volume", None),
                    "is_active": bool(getattr(d, "active", False)),
                }
            )
        return items

    async def transfer_playback(self, device_id: str, force_play: bool = True) -> None:
        p = self._provider_for(self.state.active_provider)
        if not p or not hasattr(p, "transfer_playback"):
            return None
        await p.transfer_playback(device_id, force_play)

    async def device_select(self, room: str | None, prefer_active: bool = True) -> str:
        """Pick a device id by room or active flag using async provider calls."""
        for p in self.providers.values():
            try:
                devices = await p.list_devices()
            except Exception:
                devices = []
            for d in devices:
                if room and getattr(d, "area", None) == room:
                    return d.id
                if prefer_active and getattr(d, "active", False):
                    return d.id
        return "default"

    async def start_vibe(self, name: str, **params) -> dict:
        # Placeholder: store vibe in state and return it
        return {"vibe": name, "params": params}

    async def stop_vibe(self) -> None:
        pass

    async def queue_add(self, entity) -> None:
        p = self._provider_for()
        if p:
            await p.add_to_queue(entity.get("id"), entity.get("type"))

    async def queue_clear(self) -> None:
        # best-effort per provider
        for p in self.providers.values():
            try:
                await p.create_playlist("__tmp_clear__", [])
            except Exception:
                pass

    async def state(self) -> dict:
        return {"active_provider": self.state.active_provider, "active_device": self.state.active_device}
