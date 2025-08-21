"""
Integration tests for OAuth structured logging.
"""

import pytest
import logging
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


class TestOAuthLoggingIntegration:
    """Integration tests for OAuth structured logging."""

    def test_oauth_login_url_logging_integration(self):
        """Test that oauth.login_url logs are structured correctly in integration."""
        # Capture logs
        log_records = []
        
        def capture_logs(record):
            log_records.append(record)
        
        # Add a custom handler to capture logs
        handler = logging.Handler()
        handler.emit = capture_logs
        logger = logging.getLogger('app.api.google_oauth')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        try:
            with patch.dict('os.environ', {
                'GOOGLE_CLIENT_ID': 'test_client_id',
                'GOOGLE_REDIRECT_URI': 'http://localhost:8000/callback'
            }):
                client = TestClient(app)
                response = client.get("/v1/google/auth/login_url")
                
                # Check that we got a successful response
                assert response.status_code == 200
                
                # Find the oauth.login_url log
                oauth_log = None
                for record in log_records:
                    if hasattr(record, 'msg') and record.msg == 'oauth.login_url':
                        oauth_log = record
                        break
                
                assert oauth_log is not None, "oauth.login_url log not found"
                
                # Verify the meta structure
                if hasattr(oauth_log, 'meta'):
                    meta = oauth_log.meta
                    assert meta['msg'] == "oauth.login_url"
                    assert meta['state_set'] is True
                    assert meta['next'] == "/"
                    assert meta['cookie_http_only'] is True
                    assert meta['samesite'] == "Lax"
        
        finally:
            logger.removeHandler(handler)

    def test_whoami_logging_integration(self):
        """Test that auth.whoami logs are structured correctly in integration."""
        # Capture logs
        log_records = []
        
        def capture_logs(record):
            log_records.append(record)
        
        # Add a custom handler to capture logs
        handler = logging.Handler()
        handler.emit = capture_logs
        logger = logging.getLogger('app.api.auth')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        try:
            with patch('app.deps.user.get_current_user_id', return_value="test_user"):
                client = TestClient(app)
                response = client.get("/v1/whoami")
                
                # Check that we got a successful response
                assert response.status_code == 200
                
                # Find the auth.whoami log
                whoami_log = None
                for record in log_records:
                    if hasattr(record, 'msg') and record.msg == 'auth.whoami':
                        whoami_log = record
                        break
                
                assert whoami_log is not None, "auth.whoami log not found"
                
                # Verify the meta structure
                if hasattr(whoami_log, 'meta'):
                    meta = whoami_log.meta
                    assert meta['msg'] == "auth.whoami"
                    assert meta['status'] == 200
                    assert meta['user_id'] == "test_user"
                    assert 'duration_ms' in meta
        
        finally:
            logger.removeHandler(handler)

    def test_oauth_callback_failure_logging_integration(self):
        """Test that oauth.callback.fail logs are structured correctly in integration."""
        # Capture logs
        log_records = []
        
        def capture_logs(record):
            log_records.append(record)
        
        # Add a custom handler to capture logs
        handler = logging.Handler()
        handler.emit = capture_logs
        logger = logging.getLogger('app.api.google_oauth')
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        
        try:
            with patch('app.api.google_oauth._verify_signed_state', return_value=True):
                with patch('app.integrations.google.oauth.exchange_code') as mock_exchange:
                    # Mock failed token exchange
                    mock_exchange.side_effect = Exception("Token exchange failed")
                    
                    client = TestClient(app)
                    response = client.get("/v1/google/auth/callback?code=test_code&state=test_state")
                    
                    # Check that we got an error response
                    assert response.status_code == 500
                    
                    # Find the oauth.callback.fail log
                    fail_log = None
                    for record in log_records:
                        if hasattr(record, 'msg') and record.msg == 'oauth.callback.fail':
                            fail_log = record
                            break
                    
                    assert fail_log is not None, "oauth.callback.fail log not found"
                    
                    # Verify the meta structure
                    if hasattr(fail_log, 'meta'):
                        meta = fail_log.meta
                        assert meta['msg'] == "oauth.callback.fail"
                        assert meta['state_valid'] is True
                        assert meta['token_exchange'] == "fail"
                        assert meta['google_status'] == 500
                        assert meta['reason'] == "oauth_exchange_failed"
                        assert meta['redirect'] == "/login?err=oauth_exchange_failed"
        
        finally:
            logger.removeHandler(handler)
