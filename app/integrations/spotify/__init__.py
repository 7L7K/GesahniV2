"""Spotify integration module for OAuth and Web API client."""

from .client import SpotifyClient, SpotifyAuthError, SpotifyTokens
from .oauth import SpotifyOAuth

__all__ = ["SpotifyClient", "SpotifyAuthError", "SpotifyTokens", "SpotifyOAuth"]
