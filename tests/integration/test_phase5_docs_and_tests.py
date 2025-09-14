"""Phase 5 – Docs & Tests: Comprehensive integration tests for API behavior."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tokens import create_access_token


class TestPhase5DocsAndTests:
    """Integration tests for Phase 5 requirements."""

    def create_test_token(
        self, user_id: str = "test_user", secret: str = "test_secret"
    ):
        """Create a test JWT token."""
        payload = {"user_id": user_id}
        return create_access_token(payload)

    @pytest.mark.parametrize("auth_mode", ["none", "hybrid", "strict_bearer"])
    def test_text_vs_messages_normalization(self, auth_mode, monkeypatch):
        """Test that text and messages inputs are normalized consistently."""
        # Setup environment based on auth mode
        if auth_mode == "none":
            monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")
        elif auth_mode == "hybrid":
            monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "1")
            monkeypatch.setenv("ASK_STRICT_BEARER", "0")
            monkeypatch.setenv("JWT_SECRET", "test_secret")
        elif auth_mode == "strict_bearer":
            monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "1")
            monkeypatch.setenv("ASK_STRICT_BEARER", "1")
            monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Mock the router to avoid actual LLM calls
        def mock_route_prompt(*args, **kwargs):
            # Return a simple response for testing
            return {"response": f"Mocked response for: {args[0][:50]}"}

        monkeypatch.setattr("app.main.route_prompt", mock_route_prompt)

        client = TestClient(app)

        # Test data: equivalent text and messages
        test_cases = [
            {
                "name": "simple_text",
                "text_input": {"prompt": "Hello world", "model": "test-model"},
                "messages_input": {
                    "prompt": [{"role": "user", "content": "Hello world"}],
                    "model": "test-model",
                },
            },
            {
                "name": "multi_message",
                "text_input": {
                    "prompt": "System prompt\nUser message",
                    "model": "test-model",
                },
                "messages_input": {
                    "prompt": [
                        {"role": "system", "content": "System prompt"},
                        {"role": "user", "content": "User message"},
                    ],
                    "model": "test-model",
                },
            },
            {
                "name": "complex_conversation",
                "text_input": {
                    "prompt": "You are helpful.\nHello\nHi there!\nHow can I help?",
                    "model": "test-model",
                },
                "messages_input": {
                    "prompt": [
                        {"role": "system", "content": "You are helpful."},
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there!"},
                        {"role": "user", "content": "How can I help?"},
                    ],
                    "model": "test-model",
                },
            },
        ]

        for test_case in test_cases:
            headers = {}
            if auth_mode == "strict_bearer":
                headers["Authorization"] = f"Bearer {self.create_test_token()}"

            # Test text input
            response_text = client.post(
                "/v1/ask", json=test_case["text_input"], headers=headers
            )
            assert response_text.status_code == 200
            text_data = response_text.json()

            # Test messages input
            response_messages = client.post(
                "/v1/ask", json=test_case["messages_input"], headers=headers
            )
            assert response_messages.status_code == 200
            messages_data = response_messages.json()

            # Both should have similar structure and request IDs
            assert "ok" in text_data
            assert "ok" in messages_data
            assert "rid" in text_data
            assert "rid" in messages_data
            assert "data" in text_data
            assert "data" in messages_data

            # Verify request IDs are generated consistently
            assert len(text_data["rid"]) == 8  # 8-character UUID format
            assert len(messages_data["rid"]) == 8

    def test_sse_flow_with_heartbeat(self, monkeypatch):
        """Test SSE streaming flow: route → deltas → done with heartbeat."""
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")

        # Mock streaming response
        def mock_stream_generator():
            import asyncio

            async def stream_response():
                # Route event
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "event": "route",
                            "data": {"vendor": "openai", "model": "gpt-4o"},
                        }
                    )
                    + "\n\n"
                )

                # Delta events
                deltas = ["Hello", " world", " from", " AI!"]
                for delta in deltas:
                    yield (
                        "data: "
                        + json.dumps({"event": "delta", "data": {"text": delta}})
                        + "\n\n"
                    )
                    await asyncio.sleep(0.01)

                # Done event
                yield "data: " + json.dumps({"event": "done", "data": {}}) + "\n\n"

            return stream_response()

        # Mock the router to return our streaming response
        async def mock_route_prompt(*args, **kwargs):
            return mock_stream_generator()

        monkeypatch.setattr("app.main.route_prompt", mock_route_prompt)

        client = TestClient(app)

        # Test streaming request
        response = client.post(
            "/v1/ask",
            json={"prompt": "Test streaming", "stream": True},
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events
        events = []
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                try:
                    event_data = json.loads(line[6:])  # Remove "data: " prefix
                    events.append(event_data)
                except json.JSONDecodeError:
                    continue

        # Verify event flow: route -> deltas -> done
        event_types = [event["event"] for event in events]
        assert "route" in event_types
        assert "delta" in event_types
        assert "done" in event_types

        # Verify deltas are in correct order
        delta_events = [event for event in events if event["event"] == "delta"]
        assert len(delta_events) > 0
        reconstructed_text = "".join([event["data"]["text"] for event in delta_events])
        assert "Hello world from AI!" in reconstructed_text

        # Verify route event has vendor/model info
        route_events = [event for event in events if event["event"] == "route"]
        assert len(route_events) > 0
        route_data = route_events[0]["data"]
        assert "vendor" in route_data
        assert "model" in route_data

    def test_error_mapping_auth_rate_5xx(self, monkeypatch):
        """Test error mapping for auth, rate limit, and 5xx errors."""
        client = TestClient(app)

        # Test 1: Auth error (401)
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "1")
        monkeypatch.setenv("ASK_STRICT_BEARER", "1")
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 401
        data = response.json()
        assert data["ok"] is False
        assert "error" in data
        assert data["error"]["type"] == "auth_error"

        # Test 2: Rate limit error (mock)
        def mock_rate_limit_error(*args, **kwargs):
            from fastapi import HTTPException

            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        monkeypatch.setattr("app.main.route_prompt", mock_rate_limit_error)

        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 429
        data = response.json()
        assert data["ok"] is False
        assert "error" in data
        assert data["error"]["type"] == "rate_limited"

        # Test 3: 5xx error (mock)
        def mock_5xx_error(*args, **kwargs):
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Internal server error")

        monkeypatch.setattr("app.main.route_prompt", mock_5xx_error)

        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 500
        data = response.json()
        assert data["ok"] is False
        assert "error" in data
        assert data["error"]["type"] == "downstream_error"

    def test_model_override_routing(self, monkeypatch):
        """Test model override routing behavior."""
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")

        # Mock router to capture routing decisions
        routing_calls = []

        async def mock_route_prompt(prompt, user_id, model_override=None, **kwargs):
            routing_calls.append(
                {"prompt": prompt, "model_override": model_override, "user_id": user_id}
            )
            return {"response": f"Mocked for model: {model_override}"}

        monkeypatch.setattr("app.main.route_prompt", mock_route_prompt)

        client = TestClient(app)

        test_cases = [
            {"prompt": "test", "model": "gpt-4o"},
            {"prompt": "test", "model": "llama3"},
            {"prompt": "test", "model": "gpt-3.5-turbo"},
            {"prompt": "test", "model": "llama3:8b"},
            {"prompt": "test", "model_override": "gpt-4o"},  # Legacy alias
        ]

        for test_case in test_cases:
            routing_calls.clear()

            response = client.post("/v1/ask", json=test_case)
            assert response.status_code == 200

            # Verify routing was called with correct model override
            assert len(routing_calls) == 1
            call = routing_calls[0]

            expected_model = test_case.get("model") or test_case.get("model_override")
            assert call["model_override"] == expected_model

    def test_auth_gate_behavior_strict_vs_hybrid(self, monkeypatch):
        """Test auth-gate behavior for strict bearer vs hybrid modes."""
        client = TestClient(app)

        # Test 1: No auth required
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") is not None

        # Test 2: Hybrid auth (cookie/header with JWT fallback)
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "1")
        monkeypatch.setenv("ASK_STRICT_BEARER", "0")
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Should work without explicit auth (anon user)
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") is not None

        # Test 3: Strict bearer auth
        monkeypatch.setenv("ASK_STRICT_BEARER", "1")

        # Should fail without bearer token
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 401

        # Should work with valid bearer token
        token = self.create_test_token("test_user", "test_secret")
        response = client.post(
            "/v1/ask",
            json={"prompt": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") is not None

        # Test 4: Invalid bearer token
        response = client.post(
            "/v1/ask",
            json={"prompt": "test"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_request_id_and_trace_id_headers(self, monkeypatch):
        """Test that X-Request-ID and X-Trace-ID headers are always set."""
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")

        def mock_route_prompt(*args, **kwargs):
            return {"response": "test"}

        monkeypatch.setattr("app.main.route_prompt", mock_route_prompt)

        client = TestClient(app)

        test_cases = ["/v1/ask", "/v1/ask/dry-explain", "/v1/ask/stream"]

        for endpoint in test_cases:
            # Test with provided X-Request-ID
            custom_rid = "custom123"
            response = client.post(
                endpoint, json={"prompt": "test"}, headers={"X-Request-ID": custom_rid}
            )

            assert response.status_code == 200
            assert response.headers.get("X-Request-ID") == custom_rid
            assert response.headers.get("X-Trace-ID") is not None

            # Test without X-Request-ID (should generate one)
            response = client.post(endpoint, json={"prompt": "test"})

            assert response.status_code == 200
            rid = response.headers.get("X-Request-ID")
            assert rid is not None
            assert len(rid) == 8  # 8-character format
            assert response.headers.get("X-Trace-ID") is not None

    def test_log_redaction_verbose_mode(self, monkeypatch, caplog):
        """Test log redaction with and without verbose mode."""
        monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")

        def mock_route_prompt(*args, **kwargs):
            return {"response": "test"}

        monkeypatch.setattr("app.main.route_prompt", mock_route_prompt)

        client = TestClient(app)

        # Test without verbose mode (should redact)
        monkeypatch.setenv("DEBUG_VERBOSE_PAYLOADS", "0")
        response = client.post("/v1/ask", json={"prompt": "secret information"})
        assert response.status_code == 200

        # Check logs for redaction
        log_messages = [
            record.message for record in caplog.records if "ask.entry" in record.message
        ]
        for log_msg in log_messages:
            assert "<redacted-prompt>" in log_msg or "secret information" not in log_msg

        # Test with verbose mode (should not redact)
        monkeypatch.setenv("DEBUG_VERBOSE_PAYLOADS", "1")
        caplog.clear()
        response = client.post("/v1/ask", json={"prompt": "secret information"})
        assert response.status_code == 200

        # Check logs for no redaction
        log_messages = [
            record.message for record in caplog.records if "ask.entry" in record.message
        ]
        assert any("secret information" in log_msg for log_msg in log_messages)
