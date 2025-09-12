"""Spotify integration module for OAuth and Web API client."""

from .client import SpotifyAuthError, SpotifyClient, SpotifyTokens
from .oauth import SpotifyOAuth

__all__ = ["SpotifyClient", "SpotifyAuthError", "SpotifyTokens", "SpotifyOAuth"]
