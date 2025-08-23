"""
Post-Call Processing Module

This module handles all post-call processing including:
- History logging
- Analytics recording
- Memory storage
- Claims writing
- Response caching
"""

import logging
from dataclasses import dataclass
from typing import Any

from .analytics import record
from .history import append_history
from .memory import memgpt
from .memory.vector_store import add_user_memory, cache_answer
from .memory.write_policy import memory_write_policy
from .telemetry import LogRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Post-Call Data Structures
# ---------------------------------------------------------------------------


@dataclass
class PostCallData:
    """Data structure for post-call processing."""

    prompt: str
    response: str
    vendor: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class PostCallResult:
    """Result of post-call processing."""

    history_logged: bool = False
    analytics_recorded: bool = False
    memory_stored: bool = False
    claims_written: bool = False
    response_cached: bool = False
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


# ---------------------------------------------------------------------------
# History Logging
# ---------------------------------------------------------------------------


async def log_history(data: PostCallData) -> bool:
    """
    Log the interaction to history.

    Args:
        data: Post-call data

    Returns:
        True if successfully logged, False otherwise
    """
    try:
        # Create log record
        record = LogRecord(
            req_id=data.request_id,
            prompt=data.prompt,
            engine_used=data.vendor,
            model_name=data.model,
            prompt_tokens=data.prompt_tokens,
            completion_tokens=data.completion_tokens,
            cost_usd=data.cost_usd,
            response=data.response,
            session_id=data.session_id,
            user_id=data.user_id,
        )

        # Append to history
        await append_history(record)
        logger.debug("History logged successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to log history: {e}")
        return False


# ---------------------------------------------------------------------------
# Analytics Recording
# ---------------------------------------------------------------------------


async def record_analytics(data: PostCallData) -> bool:
    """
    Record analytics for the interaction.

    Args:
        data: Post-call data

    Returns:
        True if successfully recorded, False otherwise
    """
    try:
        # Record the interaction
        await record(
            engine=data.vendor,
            fallback=False,  # TODO: Add fallback detection
            source="api",
        )

        logger.debug("Analytics recorded successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to record analytics: {e}")
        return False


# ---------------------------------------------------------------------------
# Memory Storage
# ---------------------------------------------------------------------------


def _extract_fact_from_qa(prompt: str, response: str) -> str:
    """
    Extract a fact from a Q&A interaction for memory storage.

    Args:
        prompt: The user prompt
        response: The AI response

    Returns:
        A fact extracted from the interaction
    """
    # Simple extraction: combine prompt and response
    return f"Q: {prompt}\nA: {response}"


async def store_memory(data: PostCallData) -> bool:
    """
    Store the interaction in memory if it meets the write policy.

    Args:
        data: Post-call data

    Returns:
        True if successfully stored, False otherwise
    """
    try:
        # Check if we should write to memory based on policy
        if not memory_write_policy.should_write_memory(data.response):
            logger.debug("Memory write blocked by policy")
            return False

        # Store in MemGPT
        if data.session_id and data.user_id:
            memgpt.store_interaction(
                data.prompt,
                data.response,
                session_id=data.session_id,
                user_id=data.user_id,
            )

        # Store in vector store
        if data.user_id:
            fact = _extract_fact_from_qa(data.prompt, data.response)
            add_user_memory(data.user_id, fact)

        logger.debug("Memory stored successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        return False


# ---------------------------------------------------------------------------
# Claims Writing
# ---------------------------------------------------------------------------


async def write_claims(data: PostCallData) -> bool:
    """
    Write claims based on the interaction.

    Args:
        data: Post-call data

    Returns:
        True if successfully written, False otherwise
    """
    try:
        if not data.session_id or not data.user_id:
            logger.debug("Skipping claims write - missing session_id or user_id")
            return False

        # Extract fact for claim
        fact = _extract_fact_from_qa(data.prompt, data.response)

        # Write claim
        memgpt.write_claim(
            session_id=data.session_id,
            user_id=data.user_id,
            claim_text=fact,
            evidence_links=[],
            claim_type="fact",
            entities=[],
            confidence=0.6,
        )

        logger.debug("Claims written successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to write claims: {e}")
        return False


# ---------------------------------------------------------------------------
# Response Caching
# ---------------------------------------------------------------------------


async def cache_response(data: PostCallData, cache_id: str | None = None) -> bool:
    """
    Cache the response for future use.

    Args:
        data: Post-call data
        cache_id: Optional explicit cache ID

    Returns:
        True if successfully cached, False otherwise
    """
    try:
        # Use provided cache_id or generate from prompt
        cache_answer(prompt=data.prompt, answer=data.response, cache_id=cache_id)

        logger.debug("Response cached successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to cache response: {e}")
        return False


# ---------------------------------------------------------------------------
# Unified Post-Call Processing
# ---------------------------------------------------------------------------


async def process_postcall(data: PostCallData) -> PostCallResult:
    """
    Process all post-call tasks.

    Args:
        data: Post-call data

    Returns:
        PostCallResult with processing status
    """
    result = PostCallResult()

    # Process all tasks concurrently
    tasks = [
        ("history", log_history(data)),
        ("analytics", record_analytics(data)),
        ("memory", store_memory(data)),
        ("claims", write_claims(data)),
        ("cache", cache_response(data)),
    ]

    # Execute all tasks
    for task_name, task in tasks:
        try:
            success = await task
            if task_name == "history":
                result.history_logged = success
            elif task_name == "analytics":
                result.analytics_recorded = success
            elif task_name == "memory":
                result.memory_stored = success
            elif task_name == "claims":
                result.claims_written = success
            elif task_name == "cache":
                result.response_cached = success

            if not success:
                result.errors.append(f"{task_name}_failed")

        except Exception as e:
            logger.error(f"Post-call {task_name} processing failed: {e}")
            result.errors.append(f"{task_name}_error: {str(e)}")

    # Log summary
    if result.errors:
        logger.warning(f"Post-call processing completed with errors: {result.errors}")
    else:
        logger.debug("Post-call processing completed successfully")

    return result


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


async def process_openai_response(
    prompt: str,
    response: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    session_id: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
    **kwargs: Any,
) -> PostCallResult:
    """
    Convenience function for processing OpenAI responses.

    Args:
        prompt: The user prompt
        response: The AI response
        model: The model used
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cost_usd: Cost in USD
        session_id: Optional session ID
        user_id: Optional user ID
        request_id: Optional request ID
        **kwargs: Additional metadata

    Returns:
        PostCallResult with processing status
    """
    data = PostCallData(
        prompt=prompt,
        response=response,
        vendor="openai",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata=kwargs,
    )

    return await process_postcall(data)


async def process_ollama_response(
    prompt: str,
    response: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float = 0.0,
    session_id: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
    **kwargs: Any,
) -> PostCallResult:
    """
    Convenience function for processing Ollama responses.

    Args:
        prompt: The user prompt
        response: The AI response
        model: The model used
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cost_usd: Cost in USD (default 0.0 for Ollama)
        session_id: Optional session ID
        user_id: Optional user ID
        request_id: Optional request ID
        **kwargs: Additional metadata

    Returns:
        PostCallResult with processing status
    """
    data = PostCallData(
        prompt=prompt,
        response=response,
        vendor="ollama",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata=kwargs,
    )

    return await process_postcall(data)


# ---------------------------------------------------------------------------
# Selective Processing
# ---------------------------------------------------------------------------


async def process_postcall_selective(
    data: PostCallData,
    include_history: bool = True,
    include_analytics: bool = True,
    include_memory: bool = True,
    include_claims: bool = True,
    include_cache: bool = True,
) -> PostCallResult:
    """
    Process post-call tasks selectively.

    Args:
        data: Post-call data
        include_history: Whether to log history
        include_analytics: Whether to record analytics
        include_memory: Whether to store memory
        include_claims: Whether to write claims
        include_cache: Whether to cache response

    Returns:
        PostCallResult with processing status
    """
    result = PostCallResult()

    # Process selected tasks
    if include_history:
        result.history_logged = await log_history(data)
        if not result.history_logged:
            result.errors.append("history_failed")

    if include_analytics:
        result.analytics_recorded = await record_analytics(data)
        if not result.analytics_recorded:
            result.errors.append("analytics_failed")

    if include_memory:
        result.memory_stored = await store_memory(data)
        if not result.memory_stored:
            result.errors.append("memory_failed")

    if include_claims:
        result.claims_written = await write_claims(data)
        if not result.claims_written:
            result.errors.append("claims_failed")

    if include_cache:
        result.response_cached = await cache_response(data)
        if not result.response_cached:
            result.errors.append("cache_failed")

    return result
