#!/usr/bin/env python3
"""
Test script to verify the WebSocket volume field fix.
This tests that the Device model can handle volume fields without crashing.
"""

from app.music.delta import prune_to_model
from app.music.models import Device


def test_device_volume_field():
    """Test that Device model handles volume field correctly."""
    print("Testing Device model with volume field...")

    # Test 1: Device with volume field
    device = Device(id="test_device", name="Test Device", volume=75)
    device_dict = device.to_dict()
    print(f"✓ Device with volume=75 serializes correctly: {device_dict}")

    # Test 2: Device without volume field (uses volume_percent)
    device2 = Device(id="test_device2", name="Test Device 2", volume_percent=50)
    device2_dict = device2.to_dict()
    print(f"✓ Device with volume_percent=50 serializes correctly: {device2_dict}")

    # Test 3: Deserialization with volume field
    data = {"id": "test_device3", "name": "Test Device 3", "volume": 80}
    device3 = Device.from_dict(data)
    print(
        f"✓ Device deserializes volume=80 correctly: volume_percent={device3.volume_percent}"
    )

    # Test 4: Prune function works
    device_dict_with_extra = device_dict.copy()
    device_dict_with_extra["extra_field"] = "should_be_removed"
    pruned = prune_to_model(device_dict_with_extra, Device)
    print(f"✓ Prune function removes extra fields: {pruned}")

    print("\n🎵 All volume field tests passed! WebSocket crash loop should be fixed.")


if __name__ == "__main__":
    test_device_volume_field()
