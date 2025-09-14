-- Migration: Add access_token_enc column to third_party_tokens and migrate existing rows
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

ALTER TABLE third_party_tokens RENAME TO third_party_tokens_old;

CREATE TABLE third_party_tokens (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  provider      TEXT NOT NULL,
  access_token  TEXT NOT NULL,
  access_token_enc BLOB,
  refresh_token TEXT,
  refresh_token_enc BLOB,
  envelope_key_version INTEGER DEFAULT 1,
  last_refresh_at INTEGER DEFAULT 0,
  refresh_error_count INTEGER DEFAULT 0,
  scope         TEXT,
  expires_at    INTEGER NOT NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  is_valid      INTEGER DEFAULT 1
);

INSERT INTO third_party_tokens (id, user_id, provider, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, expires_at, created_at, updated_at, is_valid)
SELECT id, user_id, provider, access_token, NULL, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, expires_at, created_at, updated_at, is_valid
FROM third_party_tokens_old;

DROP TABLE third_party_tokens_old;

COMMIT;
PRAGMA foreign_keys=on;
