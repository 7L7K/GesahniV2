"""
Fake Music Provider Tests

Tests the FakeProvider implementation:
- Happy path commands work correctly
- Invalid arguments raise typed errors
- State management is consistent
"""

import pytest

from app.music.providers.fake import FakeProvider


@pytest.mark.asyncio
async def test_fake_provider_initial_state():
    """Test that FakeProvider initializes with correct default state."""
    provider = FakeProvider()

    state = await provider.get_state()
    assert state.is_playing is False
    assert state.progress_ms == 0
    assert state.shuffle is False
    assert state.repeat == "off"

    # Should have a current track
    assert state.track is not None
    assert state.track.title == "Bohemian Rhapsody"  # First track in fake data
    assert state.track.provider == "fake"  # Track should have provider


@pytest.mark.asyncio
async def test_fake_provider_list_devices():
    """Test listing devices."""
    provider = FakeProvider()

    devices = await provider.list_devices()
    assert len(devices) == 3

    # Check device properties
    living_room = next(d for d in devices if d.id == "device1")
    assert living_room.name == "Living Room Speaker"
    assert living_room.type == "speaker"
    assert living_room.volume == 50
    assert living_room.active is True  # This device is active by default


@pytest.mark.asyncio
async def test_fake_provider_play_track():
    """Test playing a specific track."""
    provider = FakeProvider()

    # Play track1
    await provider.play("track1", "track")

    state = await provider.get_state()
    assert state.is_playing is True
    assert state.track.id == "track1"
    assert state.track.title == "Bohemian Rhapsody"
    assert state.progress_ms == 0


@pytest.mark.asyncio
async def test_fake_provider_play_search():
    """Test playing via search query."""
    provider = FakeProvider()

    # Play via search
    await provider.play("Stairway", "search")

    state = await provider.get_state()
    assert state.is_playing is True
    assert state.track.id == "track2"  # Should find "Stairway to Heaven"
    assert "Stairway" in state.track.title


@pytest.mark.asyncio
async def test_fake_provider_play_invalid_track():
    """Test playing invalid track raises error."""
    provider = FakeProvider()

    with pytest.raises(ValueError, match="Track not found"):
        await provider.play("nonexistent", "track")


@pytest.mark.asyncio
async def test_fake_provider_pause_resume():
    """Test pause and resume functionality."""
    provider = FakeProvider()

    # Start playing
    await provider.play("track1", "track")
    state = await provider.get_state()
    assert state.is_playing is True

    # Pause
    await provider.pause()
    state = await provider.get_state()
    assert state.is_playing is False

    # Resume
    await provider.resume()
    state = await provider.get_state()
    assert state.is_playing is True


@pytest.mark.asyncio
async def test_fake_provider_next_previous():
    """Test next/previous track functionality."""
    provider = FakeProvider()

    # Start with first track
    await provider.play("track1", "track")
    state = await provider.get_state()
    assert state.track.id == "track1"

    # Next track
    await provider.next()
    state = await provider.get_state()
    assert state.track.id == "track2"

    # Next track again
    await provider.next()
    state = await provider.get_state()
    assert state.track.id == "track3"

    # Previous track
    await provider.previous()
    state = await provider.get_state()
    assert state.track.id == "track2"


@pytest.mark.asyncio
async def test_fake_provider_seek():
    """Test seeking to position."""
    provider = FakeProvider()

    await provider.play("track1", "track")

    # Seek to 1 minute
    await provider.seek(60000)

    state = await provider.get_state()
    assert state.progress_ms == 60000


@pytest.mark.asyncio
async def test_fake_provider_seek_invalid_position():
    """Test seeking to invalid positions."""
    provider = FakeProvider()

    await provider.play("track1", "track")

    # Seek to negative position
    with pytest.raises(ValueError, match="Invalid position"):
        await provider.seek(-1000)

    # Seek beyond track duration (355000ms for track1)
    with pytest.raises(ValueError, match="Invalid position"):
        await provider.seek(400000)


@pytest.mark.asyncio
async def test_fake_provider_set_volume():
    """Test volume control."""
    provider = FakeProvider()

    # Set volume to 75
    await provider.set_volume(75)

    # Check device volume is updated
    devices = await provider.list_devices()
    active_device = next(d for d in devices if d.active)
    assert active_device.volume == 75


@pytest.mark.asyncio
async def test_fake_provider_set_volume_invalid():
    """Test invalid volume levels."""
    provider = FakeProvider()

    # Volume too low
    with pytest.raises(ValueError, match="Invalid volume level"):
        await provider.set_volume(-10)

    # Volume too high
    with pytest.raises(ValueError, match="Invalid volume level"):
        await provider.set_volume(150)


@pytest.mark.asyncio
async def test_fake_provider_transfer_playback():
    """Test transferring playback to different device."""
    provider = FakeProvider()

    devices = await provider.list_devices()
    bedroom_device = next(d for d in devices if d.id == "device2")

    # Transfer to bedroom device
    await provider.transfer_playback("device2")

    state = await provider.get_state()
    assert state.device.id == "device2"
    assert state.device.name == "Bedroom Speaker"

    # Check active status updated
    devices_after = await provider.list_devices()
    active_device = next(d for d in devices_after if d.active)
    assert active_device.id == "device2"


@pytest.mark.asyncio
async def test_fake_provider_transfer_invalid_device():
    """Test transferring to invalid device."""
    provider = FakeProvider()

    with pytest.raises(ValueError, match="Device not found"):
        await provider.transfer_playback("nonexistent")


@pytest.mark.asyncio
async def test_fake_provider_queue_add():
    """Test adding tracks to queue."""
    provider = FakeProvider()

    # Add a track to queue
    await provider.add_to_queue("track2", "track")

    # The queue addition is internal to the provider
    # We can't check the queue through get_state() since PlaybackState doesn't expose it
    # But the operation should succeed without error


@pytest.mark.asyncio
async def test_fake_provider_queue_add_invalid():
    """Test adding invalid track to queue."""
    provider = FakeProvider()

    with pytest.raises(ValueError, match="Track not found"):
        await provider.add_to_queue("nonexistent", "track")


@pytest.mark.asyncio
async def test_fake_provider_search():
    """Test search functionality."""
    provider = FakeProvider()

    # Search for "Queen"
    results = await provider.search("Queen", ["track"])
    assert "track" in results
    assert len(results["track"]) == 1
    assert results["track"][0].title == "Bohemian Rhapsody"

    # Search for non-existent track
    results = await provider.search("nonexistent", ["track"])
    assert len(results["track"]) == 0


@pytest.mark.asyncio
async def test_fake_provider_capabilities():
    """Test provider capabilities."""
    provider = FakeProvider()

    capabilities = provider.capabilities()
    expected_caps = {
        "play",
        "pause",
        "resume",
        "next",
        "previous",
        "seek",
        "volume",
        "device_transfer",
        "queue",
        "search",
    }
    assert capabilities == expected_caps


@pytest.mark.asyncio
async def test_fake_provider_progress_tracking():
    """Test that progress tracking works correctly."""
    provider = FakeProvider()

    # Start playing
    await provider.play("track1", "track")
    start_time = await provider.get_state()
    initial_progress = start_time.progress_ms

    # Wait a bit and check progress advances when playing
    import asyncio

    await asyncio.sleep(0.1)

    mid_state = await provider.get_state()
    assert mid_state.progress_ms > initial_progress

    # Pause and check progress stops advancing
    await provider.pause()
    pause_progress = mid_state.progress_ms

    await asyncio.sleep(0.1)
    after_pause_state = await provider.get_state()
    assert after_pause_state.progress_ms == pause_progress


@pytest.mark.asyncio
async def test_fake_provider_unsupported_features():
    """Test that unsupported features raise NotImplementedError."""
    provider = FakeProvider()

    with pytest.raises(NotImplementedError):
        await provider.create_playlist("test", [])

    with pytest.raises(NotImplementedError):
        await provider.like_track("track1")

    with pytest.raises(NotImplementedError):
        await provider.recommendations({}, {})
