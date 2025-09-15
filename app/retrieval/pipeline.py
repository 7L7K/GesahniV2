"""
Retrieval pipeline module.

This module provides the main retrieval pipeline functionality.
For backward compatibility, it imports the implementation from pipeline_legacy.
"""

from .pipeline_legacy import run_pipeline

__all__ = ["run_pipeline"]
