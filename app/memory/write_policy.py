"""Memory write policies to control when memories and profiles are written.

This module implements policies to prevent low-quality or redundant memory writes
based on response characteristics like length, confidence, and content quality.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


class MemoryWritePolicy:
    """Policy to determine if memory/profile writes should be allowed."""

    def __init__(self):
        # Minimum response length to allow memory writes (characters)
        self.min_response_length = int(os.getenv("MEMORY_MIN_RESPONSE_LENGTH", "50"))

        # Minimum response length to allow profile writes (characters)
        self.min_profile_response_length = int(
            os.getenv("PROFILE_MIN_RESPONSE_LENGTH", "20")
        )

        # Low confidence indicators that should prevent writes
        self.low_confidence_patterns = [
            r"\b(i don't know|i'm not sure|i can't|unable to|sorry,? i|i apologize)\b",
            r"\b(no information|no data|not available|not found)\b",
            r"\b(error|failed|unavailable|offline)\b",
            r"\b(please try|please check|please verify)\b",
            r"\b(contact support|contact admin|ask administrator)\b",
        ]

        # Compile patterns for efficiency
        self.low_confidence_regex = re.compile(
            "|".join(self.low_confidence_patterns), re.IGNORECASE
        )

        # Enable/disable policies
        self.enable_memory_policy = os.getenv(
            "ENABLE_MEMORY_WRITE_POLICY", "1"
        ).lower() in {"1", "true", "yes", "on"}
        self.enable_profile_policy = os.getenv(
            "ENABLE_PROFILE_WRITE_POLICY", "1"
        ).lower() in {"1", "true", "yes", "on"}

        logger.info(
            "Memory write policy initialized",
            extra={
                "meta": {
                    "min_response_length": self.min_response_length,
                    "min_profile_response_length": self.min_profile_response_length,
                    "enable_memory_policy": self.enable_memory_policy,
                    "enable_profile_policy": self.enable_profile_policy,
                }
            },
        )

    def should_write_memory(
        self, response_text: str, confidence: float | None = None
    ) -> bool:
        """Determine if a memory write should be allowed based on response characteristics."""
        if not self.enable_memory_policy:
            return True

        if not response_text or not response_text.strip():
            logger.debug("Memory write blocked: empty response")
            return False

        # Check minimum length
        if len(response_text.strip()) < self.min_response_length:
            logger.debug(
                "Memory write blocked: response too short",
                extra={
                    "meta": {
                        "length": len(response_text),
                        "min_required": self.min_response_length,
                    }
                },
            )
            return False

        # Check for low confidence indicators
        if self._has_low_confidence_indicators(response_text):
            logger.debug("Memory write blocked: low confidence indicators detected")
            return False

        # Check confidence score if provided
        if confidence is not None and confidence < 0.7:
            logger.debug(
                "Memory write blocked: low confidence score",
                extra={"meta": {"confidence": confidence}},
            )
            return False

        logger.debug("Memory write allowed")
        return True

    def should_write_profile(
        self, response_text: str, profile_key: str, confidence: float | None = None
    ) -> bool:
        """Determine if a profile write should be allowed based on response characteristics."""
        if not self.enable_profile_policy:
            return True

        if not response_text or not response_text.strip():
            logger.debug("Profile write blocked: empty response")
            return False

        # Check minimum length
        if len(response_text.strip()) < self.min_profile_response_length:
            logger.debug(
                "Profile write blocked: response too short",
                extra={
                    "meta": {
                        "length": len(response_text),
                        "min_required": self.min_profile_response_length,
                    }
                },
            )
            return False

        # Check for low confidence indicators
        if self._has_low_confidence_indicators(response_text):
            logger.debug("Profile write blocked: low confidence indicators detected")
            return False

        # Check confidence score if provided
        if (
            confidence is not None and confidence < 0.8
        ):  # Higher threshold for profile writes
            logger.debug(
                "Profile write blocked: low confidence score",
                extra={"meta": {"confidence": confidence}},
            )
            return False

        logger.debug(
            "Profile write allowed", extra={"meta": {"profile_key": profile_key}}
        )
        return True

    def _has_low_confidence_indicators(self, text: str) -> bool:
        """Check if text contains low confidence indicators."""
        if not text:
            return True

        # Check for regex patterns
        if self.low_confidence_regex.search(text):
            return True

        # Additional heuristics
        text_lower = text.lower()

        # Very short responses
        if len(text.strip()) < 10:
            return True

        # Responses that are just punctuation or common filler
        if text.strip() in {".", "!", "?", "...", "??", "!!"}:
            return True

        # Responses that are just acknowledgments
        if text_lower in {"ok", "okay", "yes", "no", "maybe", "sure", "fine"}:
            return True

        return False


# Global instance
memory_write_policy = MemoryWritePolicy()
