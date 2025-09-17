"""Centralized model catalog for GesahniV2.

This module provides a single source of truth for all model identifiers used
throughout the application. Import from here to avoid ID drift in tests.
"""

# Chat/Text Generation Models
GPT_4O_MINI = "gpt-4o-mini"
GPT_4O = "gpt-4o"
O1_MINI = "o1-mini"

# Local LLaMA Models
LLAMA3_LATEST = "llama3:latest"

# Embedding Models
TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002"

# Audio/Transcription Models
WHISPER_1 = "whisper-1"

# Legacy Router Aliases (for backward compatibility)
GPT_BASELINE_ALIAS = "gpt-5-nano"  # maps to GPT_4O_MINI
GPT_MID_ALIAS = "gpt-4.1-nano"  # maps to GPT_4O
GPT_HEAVY_ALIAS = "gpt-4o"  # maps to GPT_4O

# All supported models
ALL_MODELS = {
    # OpenAI Chat
    GPT_4O_MINI,
    GPT_4O,
    O1_MINI,
    # LLaMA
    LLAMA3_LATEST,
    # Embeddings
    TEXT_EMBEDDING_ADA_002,
    # Audio
    WHISPER_1,
}

# Model to provider mapping
MODEL_PROVIDERS = {
    GPT_4O_MINI: "openai",
    GPT_4O: "openai",
    O1_MINI: "openai",
    LLAMA3_LATEST: "ollama",
    TEXT_EMBEDDING_ADA_002: "openai",
    WHISPER_1: "openai",
}

# Legacy alias mappings (used by router)
MODEL_ALIASES = {
    GPT_BASELINE_ALIAS: GPT_4O_MINI,
    GPT_MID_ALIAS: GPT_4O,
    GPT_HEAVY_ALIAS: GPT_4O,
}
