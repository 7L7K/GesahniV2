"""
Delta Builder for Music State Changes

Compacts state changes and emits deltas with position ticks.
Handles playing (1s ticks) vs paused (5-10s ticks).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import fields
from typing import Any

from .models import PlayerState

logger = logging.getLogger(__name__)


def prune_to_model(d: dict, model_cls) -> dict:
    """Prune dictionary to only include fields that exist in the model class.

    This prevents WebSocket crashes when unexpected fields are present in device data.
    Falls back to allowing all fields if model introspection fails.
    """
    try:
        # Try Pydantic v2 style first
        if hasattr(model_cls, "model_fields"):
            allowed = set(model_cls.model_fields.keys())
        # Try dataclass style
        elif hasattr(model_cls, "__dataclass_fields__"):
            allowed = set(model_cls.__dataclass_fields__.keys())
        # Try dataclass fields() function
        else:
            allowed = {f.name for f in fields(model_cls)}
    except Exception:
        # If introspection fails, allow all fields as safety net
        logger.warning("prune_to_model: introspection failed, allowing all fields")
        return d

    return {k: v for k, v in d.items() if k in allowed}


class DeltaBuilder:
    """Builds and emits state deltas with position tracking."""

    def __init__(self, state_getter: Callable[[], PlayerState | None]):
        self.state_getter = state_getter
        self.last_state: PlayerState | None = None
        self.last_hash: str | None = None
        self.emitter_task: asyncio.Task | None = None
        self.send_fn: Callable[[dict[str, Any]], None] | None = None
        self.is_running = False

    async def start_emitter(
        self, send_fn: Callable[[dict[str, Any]], None], send_initial_state: bool = True
    ) -> None:
        """Start the delta emitter with the given send function."""
        self.send_fn = send_fn
        self.is_running = True

        # Send initial state if requested
        if send_initial_state:
            await self._emit_current_state()

        # Start background emitter
        self.emitter_task = asyncio.create_task(self._emitter_loop())

    async def stop_emitter(self) -> None:
        """Stop the delta emitter."""
        self.is_running = False
        if self.emitter_task:
            self.emitter_task.cancel()
            try:
                await self.emitter_task
            except asyncio.CancelledError:
                pass

    async def _emitter_loop(self) -> None:
        """Main emitter loop that sends deltas at appropriate intervals."""
        while self.is_running:
            try:
                # Get current state
                current_state = self.state_getter()
                if not current_state:
                    await asyncio.sleep(5.0)  # Wait if no state available
                    continue

                # Check if state has changed
                current_hash = current_state.state_hash()
                if current_hash != self.last_hash:
                    # State changed - emit full delta
                    await self._emit_delta(current_state, full=True)
                    self.last_state = current_state.clone()
                    self.last_hash = current_hash
                else:
                    # No state change - emit position tick if playing
                    if current_state.is_playing:
                        await self._emit_position_tick(current_state)

                # Sleep based on playing state
                sleep_time = (
                    1.0 if current_state.is_playing else 8.0
                )  # 5-10s when paused
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Delta emitter error: %s", e)
                await asyncio.sleep(5.0)  # Back off on errors

    async def _emit_current_state(self) -> None:
        """Emit the current full state."""
        current_state = self.state_getter()
        if current_state and self.send_fn:
            await self._emit_delta(current_state, full=True)
            self.last_state = current_state.clone()
            self.last_hash = current_state.state_hash()

    async def _emit_delta(self, state: PlayerState, full: bool = False) -> None:
        """Emit a delta payload."""
        if not self.send_fn:
            return

        try:
            # Safely create state dict with device field pruning
            state_dict = state.to_dict()

            # Belt-and-suspenders: ensure device data is properly formatted
            if state.device:
                from .models import Device

                device_dict = state.device.to_dict()
                # Prune device dict to only include expected fields
                pruned_device = prune_to_model(device_dict, Device)
                state_dict["device"] = pruned_device

            # Create delta payload
            payload = {
                "type": "state_delta" if not full else "state_full",
                "proto_ver": 1,
                "ts": int(time.time() * 1000),
                "state": state_dict,
                "state_hash": state.state_hash(),
            }

            # Add changes if this is a delta (not full state)
            if not full and self.last_state:
                changes = self._compute_changes(self.last_state, state)
                if changes:
                    payload["changes"] = changes

            await self.send_fn(payload)

        except Exception as e:
            logger.error("Failed to emit delta: %s", e)

    async def _emit_position_tick(self, state: PlayerState) -> None:
        """Emit a position tick when playing."""
        if not self.send_fn:
            return

        try:
            # Calculate current position based on server timestamp
            time_since_position = time.time() - state.server_ts_at_position
            current_progress = state.progress_ms + int(time_since_position * 1000)

            # Don't emit if position hasn't changed meaningfully
            if (
                self.last_state
                and abs(current_progress - self.last_state.progress_ms) < 500
            ):
                return

            payload = {
                "type": "position_tick",
                "proto_ver": 1,
                "ts": int(time.time() * 1000),
                "progress_ms": current_progress,
                "server_ts_at_position": state.server_ts_at_position,
                "is_playing": True,
            }

            await self.send_fn(payload)

        except Exception as e:
            logger.error("Failed to emit position tick: %s", e)

    def _compute_changes(
        self, old_state: PlayerState, new_state: PlayerState
    ) -> dict[str, Any]:
        """Compute the changes between two states."""
        changes = {}

        # Compare simple fields
        for field in ["is_playing", "shuffle", "repeat", "volume_percent", "provider"]:
            old_val = getattr(old_state, field)
            new_val = getattr(new_state, field)
            if old_val != new_val:
                changes[field] = {"old": old_val, "new": new_val}

        # Compare progress (with tolerance)
        progress_diff = abs(new_state.progress_ms - old_state.progress_ms)
        if progress_diff > 1000:  # More than 1 second difference
            changes["progress_ms"] = {
                "old": old_state.progress_ms,
                "new": new_state.progress_ms,
            }

        # Compare track
        if (
            (
                old_state.track
                and new_state.track
                and old_state.track.id != new_state.track.id
            )
            or (old_state.track is None and new_state.track is not None)
            or (old_state.track is not None and new_state.track is None)
        ):
            changes["track"] = {
                "old": old_state.track.to_dict() if old_state.track else None,
                "new": new_state.track.to_dict() if new_state.track else None,
            }

        # Compare device
        if (
            (
                old_state.device
                and new_state.device
                and old_state.device.id != new_state.device.id
            )
            or (old_state.device is None and new_state.device is not None)
            or (old_state.device is not None and new_state.device is None)
        ):
            from .models import Device

            old_device_dict = None
            new_device_dict = None

            if old_state.device:
                old_device_dict = prune_to_model(old_state.device.to_dict(), Device)
            if new_state.device:
                new_device_dict = prune_to_model(new_state.device.to_dict(), Device)

            changes["device"] = {
                "old": old_device_dict,
                "new": new_device_dict,
            }

        # Compare queue length (simplified)
        if len(old_state.queue) != len(new_state.queue):
            changes["queue_length"] = {
                "old": len(old_state.queue),
                "new": len(new_state.queue),
            }

        return changes
