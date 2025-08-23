from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_TOKENS_DIR = Path(os.getenv("SPOTIFY_TOKENS_DIR", "data/spotify_tokens")).resolve()
_TOKENS_DIR.mkdir(parents=True, exist_ok=True)


def _b64(secret: str) -> str:
    return base64.b64encode(secret.encode()).decode()


@dataclass
class SpotifyTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # epoch seconds


class SpotifyAuthError(RuntimeError):
    pass


class SpotifyClient:
    """Minimal Spotify Web API client for device control and recommendations.

    Token storage: per-user JSON in ``data/spotify_tokens/<user_id>.json``.
    If absent, falls back to process-wide ``SPOTIFY_REFRESH_TOKEN``.
    """

    api_base = "https://api.spotify.com/v1"
    auth_base = "https://accounts.spotify.com/api/token"

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
        self.default_refresh = os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip()
        # Use short-lived clients per request to avoid cross-task reuse issues
        # that can occur when closing shared clients in async contexts.

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def _token_path(self) -> Path:
        return _TOKENS_DIR / f"{self.user_id}.json"

    def _read_tokens(self) -> SpotifyTokens | None:
        try:
            data = json.loads(self._token_path().read_text())
            return SpotifyTokens(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", ""),
                expires_at=float(data.get("expires_at", 0)),
            )
        except Exception:
            return None

    def _write_tokens(self, tok: SpotifyTokens) -> None:
        try:
            p = self._token_path()
            self._TOKENS_DIR = _TOKENS_DIR  # no-op to satisfy linter about attribute
            # Write atomically and set strict perms (0600)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "access_token": tok.access_token,
                        "refresh_token": tok.refresh_token,
                        "expires_at": tok.expires_at,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
            tmp.replace(p)
        except Exception:
            pass

    async def _refresh(self, refresh_token: str) -> SpotifyTokens:
        if not self.client_id or not self.client_secret:
            raise SpotifyAuthError("Missing SPOTIFY_CLIENT_ID/SECRET")
        headers = {
            "Authorization": f"Basic {_b64(self.client_id + ':' + self.client_secret)}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=10.0)) as s:
            r = await s.post(self.auth_base, data=data, headers=headers)
            if r.status_code != 200:
                raise SpotifyAuthError(f"Refresh failed: {r.status_code} {r.text}")
            js = r.json()
        access_token = js.get("access_token")
        new_refresh = js.get("refresh_token") or refresh_token
        expires_in = js.get("expires_in", 3600)
        tok = SpotifyTokens(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_at=time.time() + float(expires_in) - 60.0,
        )
        self._write_tokens(tok)
        return tok

    async def _get_access_token(self) -> str:
        tok = self._read_tokens()
        if tok and tok.access_token and time.time() < tok.expires_at:
            return tok.access_token
        # need refresh
        refresh = (tok.refresh_token if tok else None) or self.default_refresh
        if not refresh:
            raise SpotifyAuthError("No refresh token available")
        tok = await self._refresh(refresh)
        return tok.access_token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        # If we cannot obtain a token (e.g., tests without creds), surface 401-like behavior
        try:
            token = await self._get_access_token()
        except SpotifyAuthError:
            # fabricate a minimal Response with 401 semantics to allow callers to treat as unauthenticated
            class _Resp:
                status_code = 401

                def json(self):  # type: ignore
                    return {}

            return _Resp()  # type: ignore[return-value]
        url = f"{self.api_base}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        # Basic retry with jitter + simple circuit breaker on 5xx
        # cb_key = f"cb:{self.user_id}"  # intentionally unused; state key stored on instance
        state = getattr(self, "_cb", {"fail": 0, "ts": 0.0})
        self._cb = state
        if state["fail"] >= 3 and time.time() - state["ts"] < 30:

            class _Resp:
                status_code = 503

                def json(self):
                    return {"error": "circuit_open"}

            return _Resp()  # type: ignore[return-value]

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=10.0)) as s:
            attempt = 0
            while True:
                attempt += 1
                r = await s.request(
                    method, url, params=params, json=json_body, headers=headers
                )
                if r.status_code >= 500 and attempt < 3:
                    # backoff: 0.1s, 0.3s
                    await asyncio.sleep(0.1 * attempt + 0.1)
                    continue
                break
            if r.status_code >= 500:
                state["fail"] += 1
                state["ts"] = time.time()
            else:
                state["fail"] = 0
                state["ts"] = time.time()
            if r.status_code == 401:
                # Access token expired unexpectedly; force refresh once
                stored = self._read_tokens()
                try:
                    await self._refresh(stored.refresh_token if stored else self.default_refresh)  # type: ignore[arg-type]
                except SpotifyAuthError:
                    return r
                token2 = await self._get_access_token()
                headers2 = {"Authorization": f"Bearer {token2}"}
                r = await s.request(
                    method, url, params=params, json=json_body, headers=headers2
                )
            return r

    # ------------------------------------------------------------------
    # Player controls
    # ------------------------------------------------------------------
    async def devices(self) -> list[dict[str, Any]]:
        r = await self._request("GET", "/me/player/devices")
        if r.status_code != 200:
            return []
        return r.json().get("devices", [])

    async def transfer(self, device_id: str, play: bool = True) -> bool:
        r = await self._request(
            "PUT",
            "/me/player",
            json_body={"device_ids": [device_id], "play": bool(play)},
        )
        return r.status_code in (200, 202, 204)

    async def play(self, uris: list[str] | None = None) -> bool:
        body = {"uris": uris} if uris else None
        r = await self._request("PUT", "/me/player/play", json_body=body)
        return r.status_code in (200, 202, 204)

    async def pause(self) -> bool:
        r = await self._request("PUT", "/me/player/pause")
        return r.status_code in (200, 202, 204)

    async def next(self) -> bool:
        r = await self._request("POST", "/me/player/next")
        return r.status_code in (200, 202, 204)

    async def previous(self) -> bool:
        r = await self._request("POST", "/me/player/previous")
        return r.status_code in (200, 202, 204)

    async def set_volume(self, level: int) -> bool:
        level = max(0, min(100, int(level)))
        r = await self._request(
            "PUT", "/me/player/volume", params={"volume_percent": level}
        )
        return r.status_code in (200, 202, 204)

    async def get_state(self) -> dict[str, Any] | None:
        r = await self._request("GET", "/me/player")
        if r.status_code == 204:
            return None
        if r.status_code != 200:
            return None
        return r.json()

    async def get_queue(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        r = await self._request("GET", "/me/player/queue")
        if r.status_code != 200:
            return None, []
        js = r.json()
        return js.get("currently_playing"), js.get("queue", [])

    async def recommendations(
        self,
        *,
        seed_tracks: list[str] | None = None,
        target_energy: float | None = None,
        target_tempo: float | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": max(1, min(100, limit))}
        if seed_tracks:
            # Spotify requires up to 5 comma-separated track IDs (not URIs)
            ids = [t.split(":")[-1] for t in seed_tracks][:5]
            params["seed_tracks"] = ",".join(ids)
        if target_energy is not None:
            params["target_energy"] = max(0.0, min(1.0, float(target_energy)))
        if target_tempo is not None:
            params["target_tempo"] = float(target_tempo)
        r = await self._request("GET", "/recommendations", params=params)
        if r.status_code != 200:
            return []
        return r.json().get("tracks", [])


__all__ = ["SpotifyClient", "SpotifyAuthError", "SpotifyTokens"]
