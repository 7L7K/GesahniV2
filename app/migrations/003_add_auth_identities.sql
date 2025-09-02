-- Migration: Add auth_identities table and link third_party_tokens -> identity_id
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- 1) Create canonical identities table
CREATE TABLE IF NOT EXISTS auth_identities (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_iss TEXT,
  provider_sub TEXT,
  email_normalized TEXT,
  email_verified INTEGER DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_identity_provider ON auth_identities(provider, provider_iss, provider_sub);
CREATE INDEX IF NOT EXISTS ix_identity_email ON auth_identities(email_normalized);

-- 2) Add identity_id column to third_party_tokens (preserve user_id for compatibility/backfill)
ALTER TABLE third_party_tokens ADD COLUMN identity_id TEXT;

-- 3) Backfill: for each distinct (user_id, provider, provider_iss, provider_sub) create an identity
-- Use randomblob for id generation; INSERT OR IGNORE to avoid duplicates.
INSERT OR IGNORE INTO auth_identities(id, user_id, provider, provider_iss, provider_sub, email_normalized, email_verified, created_at, updated_at)
SELECT lower(hex(randomblob(16))) as id,
       user_id,
       provider,
       provider_iss,
       provider_sub,
       NULL as email_normalized,
       0 as email_verified,
       strftime('%s','now') as created_at,
       strftime('%s','now') as updated_at
FROM (
  SELECT DISTINCT user_id, provider, IFNULL(provider_iss, '') AS provider_iss, IFNULL(provider_sub, '') AS provider_sub
  FROM third_party_tokens
);

-- 4) Populate third_party_tokens.identity_id by joining on user_id+provider+provider_iss+provider_sub
UPDATE third_party_tokens
SET identity_id = (
  SELECT id FROM auth_identities ai
  WHERE ai.user_id = third_party_tokens.user_id
    AND ai.provider = third_party_tokens.provider
    AND IFNULL(ai.provider_iss,'') = IFNULL(third_party_tokens.provider_iss,'')
    AND IFNULL(ai.provider_sub,'') = IFNULL(third_party_tokens.provider_sub,'')
  LIMIT 1
)
WHERE identity_id IS NULL;

-- 5) Unique constraint for valid tokens per identity+provider
CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_identity_provider_valid ON third_party_tokens(identity_id, provider) WHERE is_valid = 1;

COMMIT;
PRAGMA foreign_keys=on;

