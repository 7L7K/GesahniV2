-- Migration: Backfill identity_id, enforce NOT NULL + FK on third_party_tokens.identity_id
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- 1) Backfill identity_id where missing by joining on user_id+provider+provider_sub+provider_iss
UPDATE third_party_tokens t
SET identity_id = (
  SELECT i.id FROM auth_identities i
  WHERE i.user_id = t.user_id
    AND i.provider = t.provider
    AND IFNULL(i.provider_sub,'') = IFNULL(t.provider_sub,'')
    AND IFNULL(i.provider_iss,'') = IFNULL(t.provider_iss,'')
  LIMIT 1
)
WHERE identity_id IS NULL;

-- 1.5) Check for tokens that still can't be backfilled - provide detailed error if any exist
CREATE TEMP TABLE migration_check AS
SELECT t.id as token_id, t.user_id, t.provider, t.provider_sub, t.provider_iss
FROM third_party_tokens t
WHERE t.identity_id IS NULL;

-- If any tokens still have NULL identity_id, show details and fail via trigger
CREATE TEMP TRIGGER migration_check_trigger
BEFORE INSERT ON third_party_tokens_new
WHEN NEW.identity_id IS NULL OR NEW.identity_id = ''
BEGIN
  SELECT RAISE(ABORT, 'Migration failed: Some tokens have NULL identity_id after backfill attempt. Run this query to see affected tokens: SELECT id, user_id, provider, provider_sub FROM third_party_tokens WHERE identity_id IS NULL; Create missing identities in auth_identities table first.');
END;

-- 2) Create a new table with FK and NOT NULL identity_id
CREATE TABLE IF NOT EXISTS third_party_tokens_new (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  identity_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_sub TEXT,
  provider_iss TEXT,
  access_token TEXT NOT NULL,
  access_token_enc BLOB,
  refresh_token TEXT,
  refresh_token_enc BLOB,
  envelope_key_version INTEGER DEFAULT 1,
  last_refresh_at INTEGER DEFAULT 0,
  refresh_error_count INTEGER DEFAULT 0,
  scope TEXT,
  service_state TEXT,
  scope_union_since INTEGER DEFAULT 0,
  scope_last_added_from TEXT,
  replaced_by_id TEXT,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  is_valid INTEGER DEFAULT 1,
  FOREIGN KEY(identity_id) REFERENCES auth_identities(id)
);

-- 3) Verify all tokens have valid identity_id before copying
-- This will trigger the migration_check_trigger if any NULL/empty identity_id exists
INSERT INTO third_party_tokens_new
SELECT id, user_id, identity_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, service_state, scope_union_since, scope_last_added_from, replaced_by_id, expires_at, created_at, updated_at, is_valid
FROM third_party_tokens;

-- 4) Clean up temp objects and replace old table
DROP TRIGGER migration_check_trigger;
DROP TABLE migration_check;
DROP TABLE third_party_tokens;
ALTER TABLE third_party_tokens_new RENAME TO third_party_tokens;

-- 5) Recreate indexes including defensive unique index covering is_valid
CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_identity_provider_valid ON third_party_tokens(identity_id, provider) WHERE is_valid = 1;
CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_identity_provider_isvalid ON third_party_tokens(identity_id, provider, is_valid);
CREATE INDEX IF NOT EXISTS idx_tokens_identity_id ON third_party_tokens(identity_id);

COMMIT;
PRAGMA foreign_keys=on;
