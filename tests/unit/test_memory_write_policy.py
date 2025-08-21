"""Tests for memory write policy functionality."""

import pytest
from app.memory.write_policy import MemoryWritePolicy


class TestMemoryWritePolicy:
    """Test memory write policy functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.policy = MemoryWritePolicy()
    
    def test_should_write_memory_short_response(self):
        """Test that short responses are blocked."""
        short_response = "ok"
        assert not self.policy.should_write_memory(short_response)
    
    def test_should_write_memory_long_response(self):
        """Test that long responses are allowed."""
        long_response = "This is a detailed response with enough content to meet the minimum length requirement for memory writes."
        assert self.policy.should_write_memory(long_response)
    
    def test_should_write_memory_low_confidence_indicators(self):
        """Test that responses with low confidence indicators are blocked."""
        low_confidence_responses = [
            "I don't know",
            "I'm not sure about that",
            "Sorry, I can't help with that",
            "No information available",
            "Please try again later",
            "Contact support for assistance",
        ]
        
        for response in low_confidence_responses:
            assert not self.policy.should_write_memory(response)
    
    def test_should_write_memory_acknowledgments(self):
        """Test that simple acknowledgments are blocked."""
        acknowledgments = ["ok", "okay", "yes", "no", "maybe", "sure", "fine"]
        
        for response in acknowledgments:
            assert not self.policy.should_write_memory(response)
    
    def test_should_write_memory_punctuation_only(self):
        """Test that punctuation-only responses are blocked."""
        punctuation_responses = [".", "!", "?", "...", "??", "!!"]
        
        for response in punctuation_responses:
            assert not self.policy.should_write_memory(response)
    
    def test_should_write_profile_short_response(self):
        """Test that short responses are blocked for profile writes."""
        short_response = "ok"
        assert not self.policy.should_write_profile(short_response, "favorite_color")
    
    def test_should_write_profile_long_response(self):
        """Test that long responses are allowed for profile writes."""
        long_response = "This is a detailed response with enough content to meet the minimum length requirement for profile writes."
        assert self.policy.should_write_profile(long_response, "favorite_color")
    
    def test_should_write_profile_low_confidence_indicators(self):
        """Test that responses with low confidence indicators are blocked for profile writes."""
        low_confidence_response = "I don't know what my favorite color is"
        assert not self.policy.should_write_profile(low_confidence_response, "favorite_color")
    
    def test_should_write_memory_with_confidence_score(self):
        """Test memory write with confidence score."""
        response = "This is a detailed response with enough content to meet the minimum length requirement for memory writes and should pass the confidence test."
        
        # High confidence should allow write
        assert self.policy.should_write_memory(response, confidence=0.8)
        
        # Low confidence should block write
        assert not self.policy.should_write_memory(response, confidence=0.5)
    
    def test_should_write_profile_with_confidence_score(self):
        """Test profile write with confidence score."""
        response = "This is a detailed response with enough content to meet the minimum length requirement for profile writes and should pass the confidence test."
        
        # High confidence should allow write
        assert self.policy.should_write_profile(response, "favorite_color", confidence=0.9)
        
        # Low confidence should block write
        assert not self.policy.should_write_profile(response, "favorite_color", confidence=0.7)
    
    def test_empty_response_blocked(self):
        """Test that empty responses are blocked."""
        assert not self.policy.should_write_memory("")
        assert not self.policy.should_write_memory(None)
        assert not self.policy.should_write_memory("   ")
        
        assert not self.policy.should_write_profile("", "favorite_color")
        assert not self.policy.should_write_profile(None, "favorite_color")
        assert not self.policy.should_write_profile("   ", "favorite_color")
