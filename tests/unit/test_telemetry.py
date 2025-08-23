"""Tests for telemetry module."""

from datetime import UTC, datetime

from app.telemetry import LogRecord, hash_user_id, log_record_var, utc_now


class TestHashUserId:
    """Test hash_user_id function."""

    def test_hash_user_id_none(self):
        """Test hashing None user ID."""
        result = hash_user_id(None)
        assert result == "anon"

    def test_hash_user_id_string(self):
        """Test hashing string user ID."""
        result = hash_user_id("user123")
        assert isinstance(result, str)
        assert len(result) == 32
        # Should be deterministic
        assert hash_user_id("user123") == result

    def test_hash_user_id_bytes(self):
        """Test hashing bytes user ID."""
        user_bytes = b"user123"
        result = hash_user_id(user_bytes)
        assert isinstance(result, str)
        assert len(result) == 32
        # Should be deterministic
        assert hash_user_id(user_bytes) == result

    def test_hash_user_id_integer(self):
        """Test hashing integer user ID."""
        result = hash_user_id(12345)
        assert isinstance(result, str)
        assert len(result) == 32
        # Should be deterministic
        assert hash_user_id(12345) == result

    def test_hash_user_id_empty_string(self):
        """Test hashing empty string."""
        result = hash_user_id("")
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_user_id_special_characters(self):
        """Test hashing user ID with special characters."""
        result = hash_user_id("user@example.com")
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_user_id_unicode(self):
        """Test hashing unicode user ID."""
        result = hash_user_id("用户123")
        assert isinstance(result, str)
        assert len(result) == 32


class TestUtcNow:
    """Test utc_now function."""

    def test_utc_now_returns_datetime(self):
        """Test that utc_now returns a datetime object."""
        result = utc_now()
        assert isinstance(result, datetime)

    def test_utc_now_has_timezone(self):
        """Test that utc_now returns datetime with timezone."""
        result = utc_now()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_utc_now_is_recent(self):
        """Test that utc_now returns a recent time."""
        result = utc_now()
        now = datetime.now(UTC)
        # Should be within 1 second
        assert abs((result - now).total_seconds()) < 1

    def test_utc_now_is_deterministic_within_test(self):
        """Test that utc_now is consistent within a test."""
        result1 = utc_now()
        result2 = utc_now()
        # Should be very close (within milliseconds)
        assert abs((result1 - result2).total_seconds()) < 0.1


class TestLogRecord:
    """Test LogRecord model."""

    def test_log_record_creation(self):
        """Test creating a LogRecord with minimal fields."""
        record = LogRecord(req_id="test-123")
        assert record.req_id == "test-123"
        assert record.prompt is None
        assert record.engine_used is None

    def test_log_record_with_all_fields(self):
        """Test creating a LogRecord with all fields."""
        record = LogRecord(
            req_id="test-123",
            prompt="test prompt",
            engine_used="gpt-4",
            response="test response",
            timestamp="2023-01-01T00:00:00Z",
            session_id="session-123",
            user_id="user-123",
            channel="web",
            received_at="2023-01-01T00:00:00Z",
            started_at="2023-01-01T00:00:01Z",
            finished_at="2023-01-01T00:00:02Z",
            latency_ms=1000,
            p95_latency_ms=1200,
            status="OK",
            matched_skill="test_skill",
            match_confidence=0.95,
            intent="test_intent",
            intent_confidence=0.9,
            model_name="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            prompt_cost_usd=0.01,
            completion_cost_usd=0.005,
            cost_usd=0.015,
            ha_service_called="light.turn_on",
            entity_ids=["light.living_room"],
            state_before={"state": "off"},
            state_after={"state": "on"},
            rag_top_k=5,
            rag_doc_ids=["doc1", "doc2"],
            rag_scores=[0.9, 0.8],
            embed_tokens=50,
            retrieval_count=2,
            cache_hit=False,
            route_reason="skill_match",
            retrieved_tokens=100,
            self_check_score=0.95,
            escalated=False,
            auth_event_type="finish.start",
            auth_user_id="user-123",
            auth_source="cookie",
            auth_jwt_status="ok",
            auth_session_ready=True,
            auth_is_authenticated=True,
            auth_lock_reason="rate_limit",
            auth_boot_phase=False,
            profile_facts_keys=["fact1", "fact2"],
            facts_block="test_block",
            route_trace=["step1", "step2"],
            tts_engine="openai",
            tts_tier="standard",
            tts_chars=100,
            tts_minutes=0.5,
            tts_cost_usd=0.01
        )
        
        assert record.req_id == "test-123"
        assert record.prompt == "test prompt"
        assert record.engine_used == "gpt-4"
        assert record.response == "test response"
        assert record.timestamp == "2023-01-01T00:00:00Z"
        assert record.session_id == "session-123"
        assert record.user_id == "user-123"
        assert record.channel == "web"
        assert record.received_at == "2023-01-01T00:00:00Z"
        assert record.started_at == "2023-01-01T00:00:01Z"
        assert record.finished_at == "2023-01-01T00:00:02Z"
        assert record.latency_ms == 1000
        assert record.p95_latency_ms == 1200
        assert record.status == "OK"
        assert record.matched_skill == "test_skill"
        assert record.match_confidence == 0.95
        assert record.intent == "test_intent"
        assert record.intent_confidence == 0.9
        assert record.model_name == "gpt-4"
        assert record.prompt_tokens == 100
        assert record.completion_tokens == 50
        assert record.prompt_cost_usd == 0.01
        assert record.completion_cost_usd == 0.005
        assert record.cost_usd == 0.015
        assert record.ha_service_called == "light.turn_on"
        assert record.entity_ids == ["light.living_room"]
        assert record.state_before == {"state": "off"}
        assert record.state_after == {"state": "on"}
        assert record.rag_top_k == 5
        assert record.rag_doc_ids == ["doc1", "doc2"]
        assert record.rag_scores == [0.9, 0.8]
        assert record.embed_tokens == 50
        assert record.retrieval_count == 2
        assert record.cache_hit is False
        assert record.route_reason == "skill_match"
        assert record.retrieved_tokens == 100
        assert record.self_check_score == 0.95
        assert record.escalated is False
        assert record.auth_event_type == "finish.start"
        assert record.auth_user_id == "user-123"
        assert record.auth_source == "cookie"
        assert record.auth_jwt_status == "ok"
        assert record.auth_session_ready is True
        assert record.auth_is_authenticated is True
        assert record.auth_lock_reason == "rate_limit"
        assert record.auth_boot_phase is False
        assert record.profile_facts_keys == ["fact1", "fact2"]
        assert record.facts_block == "test_block"
        assert record.route_trace == ["step1", "step2"]
        assert record.tts_engine == "openai"
        assert record.tts_tier == "standard"
        assert record.tts_chars == 100
        assert record.tts_minutes == 0.5
        assert record.tts_cost_usd == 0.01

    def test_log_record_optional_fields(self):
        """Test that optional fields default to None."""
        record = LogRecord(req_id="test-123")
        assert record.prompt is None
        assert record.engine_used is None
        assert record.response is None
        assert record.timestamp is None
        assert record.session_id is None
        assert record.user_id is None
        assert record.channel is None
        assert record.received_at is None
        assert record.started_at is None
        assert record.finished_at is None
        assert record.latency_ms is None
        assert record.p95_latency_ms is None
        assert record.status is None
        assert record.matched_skill is None
        assert record.match_confidence is None
        assert record.intent is None
        assert record.intent_confidence is None
        assert record.model_name is None
        assert record.prompt_tokens is None
        assert record.completion_tokens is None
        assert record.prompt_cost_usd is None
        assert record.completion_cost_usd is None
        assert record.cost_usd is None
        assert record.ha_service_called is None
        assert record.entity_ids is None
        assert record.state_before is None
        assert record.state_after is None
        assert record.rag_top_k is None
        assert record.rag_doc_ids is None
        assert record.rag_scores is None
        assert record.embed_tokens is None
        assert record.retrieval_count is None
        assert record.cache_hit is None
        assert record.route_reason is None
        assert record.retrieved_tokens is None
        assert record.self_check_score is None
        assert record.escalated is None
        assert record.auth_event_type is None
        assert record.auth_user_id is None
        assert record.auth_source is None
        assert record.auth_jwt_status is None
        assert record.auth_session_ready is None
        assert record.auth_is_authenticated is None
        assert record.auth_lock_reason is None
        assert record.auth_boot_phase is None
        assert record.profile_facts_keys is None
        assert record.facts_block is None
        assert record.route_trace is None
        assert record.tts_engine is None
        assert record.tts_tier is None
        assert record.tts_chars is None
        assert record.tts_minutes is None
        assert record.tts_cost_usd is None


class TestLogRecordVar:
    """Test log_record_var context variable."""

    def test_log_record_var_default(self):
        """Test that log_record_var defaults to None."""
        assert log_record_var.get() is None

    def test_log_record_var_set_get(self):
        """Test setting and getting log_record_var."""
        record = LogRecord(req_id="test-123")
        token = log_record_var.set(record)
        assert log_record_var.get() == record
        log_record_var.reset(token)
        assert log_record_var.get() is None
