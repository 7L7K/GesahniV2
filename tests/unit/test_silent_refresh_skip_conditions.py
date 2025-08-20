import pytest
from unittest.mock import Mock, patch
from fastapi import Request, Response
from app.middleware import silent_refresh_middleware


@pytest.fixture
def mock_request():
    request = Mock(spec=Request)
    request.url.path = "/v1/test"
    request.cookies = {}
    request.headers = {}
    return request


@pytest.fixture
def mock_response():
    response = Mock(spec=Response)
    response.status_code = 200
    response.headers = Mock()
    response.headers.getlist = Mock(return_value=[])
    return response


@pytest.mark.asyncio
async def test_skip_non_v1_paths(mock_request, mock_response):
    """Test that silent refresh is skipped for non-v1 paths."""
    mock_request.url.path = "/static/file.js"
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_logout_paths_ends_with_logout(mock_request, mock_response):
    """Test that silent refresh is skipped for paths ending with /logout."""
    mock_request.url.path = "/v1/auth/logout"
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_logout_paths_contains_auth_logout(mock_request, mock_response):
    """Test that silent refresh is skipped for paths containing /auth/logout."""
    mock_request.url.path = "/v1/some/path/auth/logout/extra"
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_x_logout_header(mock_request, mock_response):
    """Test that silent refresh is skipped when X-Logout header is present."""
    mock_request.headers = {"X-Logout": "true"}
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_auth_cookie_deletion_access_token(mock_request, mock_response):
    """Test that silent refresh is skipped when access_token is deleted with Max-Age=0."""
    mock_response.headers.getlist.return_value = [
        "access_token=; Max-Age=0; Path=/; HttpOnly"
    ]
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_auth_cookie_deletion_refresh_token(mock_request, mock_response):
    """Test that silent refresh is skipped when refresh_token is deleted with Max-Age=0."""
    mock_response.headers.getlist.return_value = [
        "refresh_token=; Max-Age=0; Path=/; HttpOnly"
    ]
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_auth_cookie_deletion_session(mock_request, mock_response):
    """Test that silent refresh is skipped when __session is deleted with Max-Age=0."""
    mock_response.headers.getlist.return_value = [
        "__session=; Max-Age=0; Path=/; HttpOnly"
    ]
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_skip_204_status_code(mock_request, mock_response):
    """Test that silent refresh is skipped for 204 responses."""
    mock_response.status_code = 204
    
    async def mock_call_next(req):
        return mock_response
    
    result = await silent_refresh_middleware(mock_request, mock_call_next)
    assert result == mock_response


@pytest.mark.asyncio
async def test_do_not_skip_normal_v1_path(mock_request, mock_response):
    """Test that silent refresh is NOT skipped for normal v1 paths."""
    mock_request.url.path = "/v1/ask"
    mock_request.cookies = {"access_token": "valid_token"}
    
    async def mock_call_next(req):
        return mock_response
    
    # Mock JWT decode to return a valid payload
    with patch('app.middleware.jwt.decode') as mock_jwt_decode:
        mock_jwt_decode.return_value = {
            "user_id": "test_user",
            "exp": 9999999999  # Far future expiry
        }
        
        result = await silent_refresh_middleware(mock_request, mock_call_next)
        assert result == mock_response
        # Verify that JWT decode was called (indicating refresh logic was attempted)
        mock_jwt_decode.assert_called_once()
