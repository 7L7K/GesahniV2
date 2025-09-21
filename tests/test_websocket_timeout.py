"""Tests for WebSocket timeout middleware and utilities."""

import pytest
import os
from unittest.mock import AsyncMock, Mock

from app.middleware.websocket_timeout import WebSocketTimeoutManager


class TestWebSocketTimeoutManager:
    """Test cases for WebSocket timeout management."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket for testing."""
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.close = AsyncMock()
        return ws

    def test_initialization(self, mock_websocket):
        """Test WebSocketTimeoutManager initialization."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        assert manager.ws == mock_websocket
        assert manager.user_id == "test_user"
        assert manager.connected_at > 0
        assert manager.last_activity > 0
        assert manager.last_pong > 0

    def test_timeout_configuration_from_env(self, mock_websocket):
        """Test that timeout configuration is read from environment variables."""
        # Set environment variables
        os.environ["WS_HEARTBEAT_INTERVAL"] = "45.0"
        os.environ["WS_CONNECTION_TIMEOUT"] = "600.0"
        os.environ["WS_MESSAGE_TIMEOUT"] = "2.0"
        os.environ["WS_IDLE_TIMEOUT"] = "120.0"
        os.environ["WS_PING_INTERVAL"] = "30.0"
        os.environ["WS_PONG_TIMEOUT"] = "90.0"
        
        try:
            manager = WebSocketTimeoutManager(mock_websocket, "test_user")
            
            assert manager.heartbeat_interval == 45.0
            assert manager.connection_timeout == 600.0
            assert manager.message_timeout == 2.0
            assert manager.idle_timeout == 120.0
            assert manager.ping_interval == 30.0
            assert manager.pong_timeout == 90.0
        finally:
            # Clean up environment variables
            for key in [
                "WS_HEARTBEAT_INTERVAL", "WS_CONNECTION_TIMEOUT", "WS_MESSAGE_TIMEOUT",
                "WS_IDLE_TIMEOUT", "WS_PING_INTERVAL", "WS_PONG_TIMEOUT"
            ]:
                os.environ.pop(key, None)

    def test_send_json_with_timeout_success(self, mock_websocket):
        """Test successful JSON send with timeout."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        test_data = {"type": "test", "data": "hello"}
        
        async def test_send():
            result = await manager.send_json_with_timeout(test_data)
            assert result is True
            mock_websocket.send_json.assert_called_once_with(test_data)
        
        asyncio.run(test_send())

    def test_send_json_with_timeout_failure(self, mock_websocket):
        """Test JSON send timeout handling."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        test_data = {"type": "test", "data": "hello"}
        
        # Mock timeout
        mock_websocket.send_json.side_effect = asyncio.TimeoutError()
        
        async def test_send():
            result = await manager.send_json_with_timeout(test_data, timeout=0.1)
            assert result is False
        
        asyncio.run(test_send())

    def test_send_text_with_timeout_success(self, mock_websocket):
        """Test successful text send with timeout."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        test_text = "ping"
        
        async def test_send():
            result = await manager.send_text_with_timeout(test_text)
            assert result is True
            mock_websocket.send_text.assert_called_once_with(test_text)
        
        asyncio.run(test_send())

    def test_receive_with_timeout_success(self, mock_websocket):
        """Test successful receive with timeout."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        mock_websocket.receive_text.return_value = "pong"
        
        async def test_receive():
            result = await manager.receive_with_timeout(timeout=1.0)
            assert result == "pong"
            mock_websocket.receive_text.assert_called_once()
        
        asyncio.run(test_receive())

    def test_receive_with_timeout_failure(self, mock_websocket):
        """Test receive timeout handling."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Mock timeout - receive_text never completes
        async def slow_receive():
            await asyncio.sleep(10)  # Longer than timeout
            return "too_late"
        
        mock_websocket.receive_text.side_effect = slow_receive
        
        async def test_receive():
            result = await manager.receive_with_timeout(timeout=0.1)
            assert result is None
        
        asyncio.run(test_receive())

    def test_activity_tracking(self, mock_websocket):
        """Test activity tracking functionality."""
        import time
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        initial_activity = manager.last_activity
        
        # Wait a bit
        time.sleep(0.01)
        
        # Update activity
        manager.update_activity()
        
        assert manager.last_activity > initial_activity
        assert manager.last_pong > initial_activity

    def test_idle_detection(self, mock_websocket):
        """Test idle connection detection."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Should not be idle initially
        assert not manager.is_idle()
        
        # Set a very short idle timeout for testing
        manager.idle_timeout = 0.001
        
        # Wait for idle timeout
        import time
        time.sleep(0.002)
        
        # Should be idle now
        assert manager.is_idle()

    def test_pong_timeout_detection(self, mock_websocket):
        """Test pong timeout detection."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Should not be pong timeout initially
        assert not manager.is_pong_timeout()
        
        # Set a very short pong timeout for testing
        manager.pong_timeout = 0.001
        
        # Wait for pong timeout
        import time
        time.sleep(0.002)
        
        # Should be pong timeout now
        assert manager.is_pong_timeout()

    def test_should_ping(self, mock_websocket):
        """Test ping timing logic."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Should not need to ping initially
        assert not manager.should_ping()
        
        # Set a very short ping interval for testing
        manager.ping_interval = 0.001
        
        # Wait for ping interval
        import time
        time.sleep(0.002)
        
        # Should need to ping now
        assert manager.should_ping()

    def test_connection_age(self, mock_websocket):
        """Test connection age calculation."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Age should be small initially
        age = manager.connection_age()
        assert age >= 0
        assert age < 1.0  # Should be less than 1 second

    def test_connection_timeout_detection(self, mock_websocket):
        """Test connection timeout detection."""
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Should not be connection timeout initially
        assert not manager.is_connection_timeout()
        
        # Set a very short connection timeout for testing
        manager.connection_timeout = 0.001
        
        # Wait for connection timeout
        import time
        time.sleep(0.002)
        
        # Should be connection timeout now
        assert manager.is_connection_timeout()

    def test_graceful_close(self, mock_websocket):
        """Test graceful connection close."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        async def test_close():
            await manager.graceful_close(code=1000, reason="test_close")
            mock_websocket.close.assert_called_once_with(code=1000, reason="test_close")
        
        asyncio.run(test_close())

    def test_heartbeat_success(self, mock_websocket):
        """Test successful heartbeat cycle."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Mock successful ping/pong cycle
        mock_websocket.send_text.return_value = None
        mock_websocket.receive_text.return_value = "pong"
        
        # Set short ping interval to trigger heartbeat
        manager.ping_interval = 0.001
        manager.pong_timeout = 10.0  # Long enough for test
        
        async def test_heartbeat():
            # Wait for ping interval
            import time
            time.sleep(0.002)
            
            result = await manager.handle_heartbeat()
            assert result is True
            mock_websocket.send_text.assert_called_with("ping")
        
        asyncio.run(test_heartbeat())

    def test_heartbeat_no_pong(self, mock_websocket):
        """Test heartbeat failure when no pong received."""
        import asyncio
        
        manager = WebSocketTimeoutManager(mock_websocket, "test_user")
        
        # Mock ping success but no pong response
        mock_websocket.send_text.return_value = None
        mock_websocket.receive_text.return_value = "not_pong"
        
        # Set short ping interval to trigger heartbeat
        manager.ping_interval = 0.001
        manager.pong_timeout = 10.0  # Long enough for test
        
        async def test_heartbeat():
            # Wait for ping interval
            import time
            time.sleep(0.002)
            
            result = await manager.handle_heartbeat()
            assert result is False
        
        asyncio.run(test_heartbeat())
