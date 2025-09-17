from __future__ import annotations

import logging
import time

from app.integrations.spotify.client import SpotifyAuthError, SpotifyClient

from .base import Device, PlaybackState, Track

logger = logging.getLogger(__name__)


def log_spotify_provider(
    operation: str, user_id: str, details: dict = None, level: str = "info"
):
    """Enhanced Spotify provider logging."""
    details = details or {}
    log_data = {
        "operation": operation,
        "user_id": user_id,
        "component": "spotify_provider",
        "timestamp": time.time(),
        **details,
    }

    if level == "debug":
        logger.debug(
            f"🎵 SPOTIFY PROVIDER {operation.upper()}", extra={"meta": log_data}
        )
    elif level == "warning":
        logger.warning(
            f"🎵 SPOTIFY PROVIDER {operation.upper()}", extra={"meta": log_data}
        )
    elif level == "error":
        logger.error(
            f"🎵 SPOTIFY PROVIDER {operation.upper()}", extra={"meta": log_data}
        )
    else:
        logger.info(
            f"🎵 SPOTIFY PROVIDER {operation.upper()}", extra={"meta": log_data}
        )


class SpotifyProvider:
    """Spotify provider using the new unified integration for playback and device management."""

    name = "spotify"

    def __init__(self, user_id: str = "default") -> None:
        log_spotify_provider(
            "provider_init",
            user_id,
            {
                "message": "Initializing SpotifyProvider",
                "user_id": user_id,
                "default_user": user_id == "default",
            },
        )

        self.user_id = user_id
        try:
            self.client = SpotifyClient(user_id)
            log_spotify_provider(
                "provider_init_success",
                user_id,
                {
                    "message": "SpotifyProvider initialized successfully",
                    "client_created": True,
                },
            )
        except Exception as e:
            log_spotify_provider(
                "provider_init_error",
                user_id,
                {
                    "message": "Failed to initialize SpotifyProvider",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "level": "error",
                },
                level="error",
            )
            raise

    async def _ensure_client(self) -> SpotifyClient:
        """Ensure we have a client with valid tokens."""
        return self.client

    # ---- Base provider interface (adapted) ---------------------------------
    async def play(
        self,
        entity_id: str,
        entity_type: str,
        *,
        device_id: str | None = None,
        position_ms: int | None = None,
    ) -> None:
        """Start or resume playback for a track/album/playlist.

        For tracks: send URIs. For album/playlist: use context_uri.
        If device_id is provided, transfer playback first (best-effort).
        """
        try:
            client = await self._ensure_client()
            if device_id:
                try:
                    await client.transfer_playback(device_id, play=True)
                except Exception as e:
                    logger.debug(
                        "Failed to transfer Spotify playback to device",
                        extra={
                            "meta": {
                                "user_id": self.user_id,
                                "device_id": device_id,
                                "error": str(e),
                            }
                        },
                    )

            uri = entity_id if ":" in (entity_id or "") else None

            uris = None
            context_uri = None
            et = (entity_type or "track").lower()
            if et == "track":
                uris = [uri or f"spotify:track:{entity_id}"] if entity_id else None
            elif et in {"album", "playlist", "artist"}:
                kind = et
                context_uri = uri or f"spotify:{kind}:{entity_id}"

            success = await client.play(uris=uris, context_uri=context_uri)
            if not success:
                raise RuntimeError("spotify_play_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify play failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def pause(self) -> None:
        """Pause playback."""
        try:
            client = await self._ensure_client()
            success = await client.pause()
            if not success:
                raise RuntimeError("spotify_pause_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify pause failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def resume(self) -> None:
        """Resume playback (PUT /me/player/play with empty body)."""
        try:
            client = await self._ensure_client()
            success = await client.play()
            if not success:
                raise RuntimeError("spotify_resume_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify resume failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def next(self) -> None:
        """Skip to next track."""
        try:
            client = await self._ensure_client()
            success = await client.next_track()
            if not success:
                raise RuntimeError("spotify_next_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify next failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def previous(self) -> None:
        """Skip to previous track."""
        try:
            client = await self._ensure_client()
            success = await client.previous_track()
            if not success:
                raise RuntimeError("spotify_previous_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify previous failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def list_devices(self) -> list[Device]:
        """Get available playback devices as Device dataclasses."""
        try:
            client = await self._ensure_client()
            devices = await client.get_devices()
            out: list[Device] = []
            for d in devices:
                out.append(
                    Device(
                        id=d.get("id") or "default",
                        name=d.get("name") or "Unknown",
                        type=d.get("type") or "unknown",
                        volume=d.get("volume_percent"),
                        active=bool(
                            d.get("is_active") or (d.get("is_restricted") in (False,))
                        ),
                    )
                )
            return out
        except SpotifyAuthError as e:
            logger.error("Spotify list_devices failed: %s", e)
            return []

    async def transfer_playback(self, device_id: str, force_play: bool = True) -> None:
        try:
            client = await self._ensure_client()
            ok = await client.transfer_playback(device_id, play=force_play)
            if not ok:
                raise RuntimeError("spotify_transfer_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify transfer failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def get_state(self) -> PlaybackState:
        log_spotify_provider(
            "get_state_start",
            self.user_id,
            {"message": "Starting get_state request", "method": "get_state"},
        )

        try:
            client = await self._ensure_client()
            log_spotify_provider(
                "client_ensured",
                self.user_id,
                {"message": "Client ensured for get_state"},
            )

            st = await client.get_currently_playing()
            log_spotify_provider(
                "currently_playing_result",
                self.user_id,
                {
                    "message": "Received currently playing data",
                    "has_data": st is not None,
                    "data_keys": list(st.keys()) if st else None,
                },
            )

            track = None
            device = None

            if st:
                item = (st or {}).get("item") or {}
                if item:
                    track = Track(
                        id=item.get("id") or "",
                        title=item.get("name") or "",
                        artist=", ".join(
                            [a.get("name", "") for a in item.get("artists", [])]
                        ),
                        album=(item.get("album") or {}).get("name", ""),
                        duration_ms=int(item.get("duration_ms") or 0),
                        explicit=bool(item.get("explicit")),
                        provider=self.name,
                    )
                    log_spotify_provider(
                        "track_parsed",
                        self.user_id,
                        {
                            "message": "Track data parsed successfully",
                            "track_id": track.id,
                            "track_title": track.title,
                            "track_artist": track.artist,
                        },
                    )

                dev = (st or {}).get("device") or {}
                if dev:
                    device = Device(
                        id=dev.get("id") or "default",
                        name=dev.get("name") or "Unknown",
                        type=dev.get("type") or "unknown",
                        volume=dev.get("volume_percent"),
                        active=bool(dev.get("is_active")),
                    )
                    log_spotify_provider(
                        "device_parsed",
                        self.user_id,
                        {
                            "message": "Device data parsed successfully",
                            "device_id": device.id,
                            "device_name": device.name,
                            "device_active": device.active,
                        },
                    )

            playback_state = PlaybackState(
                is_playing=bool(st.get("is_playing") if st else False),
                progress_ms=int(
                    st.get("progress_ms")
                    if st and st.get("progress_ms") is not None
                    else 0
                ),
                track=track,
                device=device,
                shuffle=False,
                repeat="off",
            )

            log_spotify_provider(
                "get_state_success",
                self.user_id,
                {
                    "message": "Playback state retrieved successfully",
                    "is_playing": playback_state.is_playing,
                    "progress_ms": playback_state.progress_ms,
                    "has_track": playback_state.track is not None,
                    "has_device": playback_state.device is not None,
                },
            )

            return playback_state

        except SpotifyAuthError as e:
            log_spotify_provider(
                "get_state_auth_error",
                self.user_id,
                {
                    "message": "Authentication error in get_state",
                    "error": str(e),
                    "level": "warning",
                },
                level="warning",
            )
            return PlaybackState(
                is_playing=False,
                progress_ms=0,
                track=None,
                device=None,
                shuffle=False,
                repeat="off",
            )
        except Exception as e:
            log_spotify_provider(
                "get_state_error",
                self.user_id,
                {
                    "message": "Unexpected error in get_state",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "level": "error",
                },
                level="error",
            )
            return PlaybackState(
                is_playing=False,
                progress_ms=0,
                track=None,
                device=None,
                shuffle=False,
                repeat="off",
            )

    async def set_volume(self, level: int) -> None:
        try:
            client = await self._ensure_client()
            ok = await client.set_volume(int(level))
            if not ok:
                raise RuntimeError("spotify_volume_failed")
        except SpotifyAuthError as e:
            logger.error("Spotify set_volume failed: %s", e)
            raise RuntimeError("spotify_auth_failed")

    async def search(self, query: str, types) -> dict[str, list[Track]]:
        try:
            client = await self._ensure_client()
            results = await client.search_tracks(query, limit=10)
            out: list[Track] = []
            for t in results:
                out.append(
                    Track(
                        id=t.get("id"),
                        title=t.get("name"),
                        artist=", ".join(
                            [a.get("name", "") for a in t.get("artists", [])]
                        ),
                        album=(t.get("album") or {}).get("name", ""),
                        duration_ms=int(t.get("duration_ms") or 0),
                        explicit=bool(t.get("explicit")),
                        provider=self.name,
                    )
                )
            return {"track": out}
        except Exception:
            return {"track": []}

    async def add_to_queue(self, entity_id: str, entity_type: str) -> None:
        # Not implemented in client; silently ignore
        return None

    async def create_playlist(self, name: str, track_ids: list[str]):
        # Not implemented for now
        return None

    async def like_track(self, track_id: str) -> None:
        # Optional, skip
        return None

    async def recommendations(self, seeds: dict, params: dict) -> list[dict]:
        try:
            client = await self._ensure_client()
            tracks = await client.get_recommendations(
                seed_tracks=seeds.get("tracks"),
                seed_artists=seeds.get("artists"),
                seed_genres=seeds.get("genres"),
                target_energy=params.get("target_energy"),
                target_tempo=params.get("target_tempo"),
                limit=int(params.get("limit", 20)),
            )
            return tracks
        except Exception:
            return []
