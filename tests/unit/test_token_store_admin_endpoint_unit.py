import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def make_client():
    from app.api.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    return TestClient(app)


def setup_function(_):
    os.environ["ADMIN_TOKEN"] = "t"
    os.environ["PYTEST_RUNNING"] = "1"


class TestTokenStoreAdminEndpoint:
    """Test the admin token store stats endpoint."""
    
    def test_admin_token_store_stats_function_direct(self):
        """Test the get_storage_stats function directly."""
        import asyncio

        from app.token_store import get_storage_stats
        
        # Test the function directly without the API layer
        result = asyncio.run(get_storage_stats())
        assert "redis_available" in result
        assert "local_storage" in result
        assert "cleanup_task_running" in result
        assert isinstance(result["local_storage"], dict)
    
    def test_admin_token_store_stats_function_with_mock(self):
        """Test the get_storage_stats function with mocked Redis."""
        import asyncio

        from app.token_store import get_storage_stats
        
        with patch('app.token_store.has_redis') as mock_has_redis:
            mock_has_redis.return_value = False
            
            result = asyncio.run(get_storage_stats())
            assert result["redis_available"] is False
            assert "local_storage" in result
            assert "cleanup_task_running" in result
