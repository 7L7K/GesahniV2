-- Migration: Create third_party_tokens table for unified token storage
-- This replaces the JSON-based token storage with a unified SQL table
-- Supports multiple providers (Spotify, Google, Apple, etc.)

CREATE TABLE IF NOT EXISTS third_party_tokens (
  id            TEXT PRIMARY KEY,           -- UUID or composite key
  user_id       TEXT NOT NULL,               -- User identifier
  provider      TEXT NOT NULL,               -- Provider name ('spotify', 'google', 'apple', etc.)
  access_token  TEXT NOT NULL,               -- Encrypted access token
  refresh_token TEXT,                        -- Encrypted refresh token (nullable)
  scope         TEXT,                        -- Token scope(s)
  expires_at    INTEGER NOT NULL,            -- Expiration timestamp (epoch seconds)
  created_at    INTEGER NOT NULL,            -- Creation timestamp (epoch seconds)
  updated_at    INTEGER NOT NULL,            -- Last update timestamp (epoch seconds)
  is_valid      INTEGER DEFAULT 1            -- Soft delete flag (1=valid, 0=invalid)
);

-- Index for efficient lookups by user and provider
CREATE INDEX IF NOT EXISTS idx_tokens_user_provider
  ON third_party_tokens (user_id, provider);

-- Index for finding expired tokens (for cleanup)
CREATE INDEX IF NOT EXISTS idx_tokens_expires_at
  ON third_party_tokens (expires_at);

-- Index for provider-specific queries
CREATE INDEX IF NOT EXISTS idx_tokens_provider
  ON third_party_tokens (provider);

-- Index for validity checks
CREATE INDEX IF NOT EXISTS idx_tokens_valid
  ON third_party_tokens (is_valid);

-- Ensure only one valid token per user-provider combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_tokens_user_provider_unique
  ON third_party_tokens (user_id, provider)
  WHERE is_valid = 1;
