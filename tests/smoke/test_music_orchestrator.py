import asyncio
import pytest

from app.music.orchestrator import MusicOrchestrator
from app.music.providers.base import Device


class _FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = []

    async def list_devices(self):
        return [
            Device(
                id="dev1", name="Living Room", type="speaker", volume=50, active=True
            )
        ]

    async def play(
        self,
        entity_id: str,
        entity_type: str,
        *,
        device_id: str | None = None,
        position_ms: int | None = None
    ):
        self.calls.append(("play", entity_id, entity_type, device_id))

    async def pause(self):
        self.calls.append(("pause",))

    async def resume(self):
        self.calls.append(("resume",))

    async def next(self):
        self.calls.append(("next",))

    async def previous(self):
        self.calls.append(("previous",))

    async def set_volume(self, level: int):
        self.calls.append(("set_volume", level))


@pytest.mark.asyncio
async def test_device_selection_prefers_active():
    orch = MusicOrchestrator([_FakeProvider()])
    dev = await orch.device_select(room=None, prefer_active=True)
    assert dev == "dev1"


@pytest.mark.asyncio
async def test_basic_commands_route_to_provider():
    p = _FakeProvider()
    orch = MusicOrchestrator([p])
    await orch.resume()
    await orch.pause()
    await orch.next()
    await orch.previous()
    await orch.set_volume(30)
    assert ("resume",) in p.calls
    assert ("pause",) in p.calls
    assert ("next",) in p.calls
    assert ("previous",) in p.calls
    assert ("set_volume", 30) in p.calls
