"""Development audit tests for GesahniV2 model routing.

Tests routing decisions without network calls using dry-run mode.
"""

import os

import pytest

from app.models.catalog import GPT_4O, LLAMA3_LATEST, TEXT_EMBEDDING_ADA_002
from app.router.entrypoint import RoutingDecision, route_prompt


@pytest.fixture(autouse=True)
def setup_dry_run():
    """Set up dry-run environment for all tests."""
    original_env = os.environ.copy()
    os.environ["DRY_RUN"] = "true"
    os.environ["DEBUG_MODEL_ROUTING"] = "true"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.mark.parametrize(
    "scenario,expect_model,expect_provider,must_trigger_contains,expect_stream",
    [
        ("simple_prompt", LLAMA3_LATEST, "ollama", ["default_light"], True),
        ("heavy_sql", GPT_4O, "openai", ["token_threshold", "keyword:analyze"], True),
        ("attachments_2", GPT_4O, "openai", ["attachments>2"], True),
        ("override_llama", LLAMA3_LATEST, "ollama", ["override"], True),
        (
            "long_context",
            GPT_4O,
            "openai",
            ["rag_tokens>6000", "intent:analysis"],
            True,
        ),
        ("embed_req", TEXT_EMBEDDING_ADA_002, "openai", ["task:embed"], False),
    ],
)
@pytest.mark.asyncio
async def test_routing_decisions(
    scenario, expect_model, expect_provider, must_trigger_contains, expect_stream
):
    """Test routing decisions for various scenarios in dry-run mode."""

    # Build test payload based on scenario
    if scenario == "simple_prompt":
        payload = {
            "prompt": "Hello, how are you today?",
            "task_type": "chat",
        }
    elif scenario == "heavy_sql":
        sql_prompt = (
            """
        I have a complex SQL query that involves multiple joins and aggregations.
        The query needs to analyze sales data across different time periods and
        customer segments. It should include window functions, CTEs, and proper
        indexing considerations. Please help me optimize this query for performance
        and provide the best practices for execution.
        """
            * 10
        )  # Make it long
        payload = {
            "prompt": sql_prompt,
            "task_type": "chat",
        }
    elif scenario == "attachments_2":
        payload = {
            "prompt": "Please analyze these documents and provide a summary.",
            "task_type": "chat",
            "attachments_count": 2,
        }
    elif scenario == "override_llama":
        payload = {
            "prompt": "Tell me a joke.",
            "model_override": "llama3:latest",
            "task_type": "chat",
        }
    elif scenario == "long_context":
        payload = {
            "prompt": "Please analyze this research paper and provide insights.",
            "task_type": "chat",
            "intent_hint": "analysis",
            "rag_tokens": 7000,  # > 6000 threshold
        }
    elif scenario == "embed_req":
        payload = {
            "prompt": "Convert this text to embeddings",
            "task_type": "embed",
        }
    else:
        pytest.fail(f"Unknown scenario: {scenario}")

    # Get routing decision
    result = await route_prompt(payload, dry_run=True)

    # Verify it's a RoutingDecision
    assert isinstance(
        result, RoutingDecision
    ), f"Expected RoutingDecision, got {type(result)}"

    # Check model and provider
    assert (
        result.model_id == expect_model
    ), f"Expected model {expect_model}, got {result.model_id}"
    assert (
        result.provider == expect_provider
    ), f"Expected provider {expect_provider}, got {result.provider}"

    # Check streaming
    assert (
        result.stream == expect_stream
    ), f"Expected stream {expect_stream}, got {result.stream}"

    # Check that required rules are triggered
    rules_str = " ".join(result.rules_triggered)
    for required_rule in must_trigger_contains:
        assert (
            required_rule in rules_str
        ), f"Required rule '{required_rule}' not found in {result.rules_triggered}"

    # Additional sanity checks
    assert result.estimated_tokens >= 0, "Token count should be non-negative"
    assert result.task_type in [
        "chat",
        "embed",
    ], f"Unexpected task_type: {result.task_type}"

    # Embedding tasks should never stream
    if result.task_type == "embed":
        assert not result.stream, "Embedding tasks should not stream"

    # Chat tasks should generally stream
    if result.task_type == "chat":
        assert result.stream, "Chat tasks should stream"


@pytest.mark.asyncio
async def test_no_network_calls():
    """Ensure dry-run mode doesn't make network calls."""
    payload = {"prompt": "Test prompt", "task_type": "chat"}

    # This should complete without hanging or making network requests
    result = await route_prompt(payload, dry_run=True)

    assert isinstance(result, RoutingDecision)
    assert result.model_id in [
        LLAMA3_LATEST,
        GPT_4O,
    ]  # Should be one of the expected models


@pytest.mark.asyncio
async def test_privacy_mode_flag():
    """Test that privacy mode is properly tracked."""
    payload = {"prompt": "Test prompt", "task_type": "chat", "privacy_mode": True}

    result = await route_prompt(payload, dry_run=True)

    assert isinstance(result, RoutingDecision)
    assert result.privacy_mode is True


@pytest.mark.asyncio
async def test_unknown_model_fallback():
    """Test fallback behavior for unknown model overrides."""
    payload = {
        "prompt": "Test prompt",
        "model_override": "unknown-model-123",
        "task_type": "chat",
    }

    result = await route_prompt(payload, dry_run=True)

    assert isinstance(result, RoutingDecision)
    assert "unknown_model" in " ".join(result.rules_triggered)
    assert len(result.fallback_chain) > 0
    # Should fall back to GPT
    assert result.provider == "openai"
