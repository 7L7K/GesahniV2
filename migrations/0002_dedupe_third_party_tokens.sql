-- migrations/0002_dedupe_third_party_tokens.sql
-- One-time dedup and index creation for third_party_tokens

-- POSTGRES
-- Keep the newest row by updated_at for each (user_id, provider)
-- NOTE: run in a safe maintenance window
-- Delete older duplicates
DELETE FROM third_party_tokens t
USING third_party_tokens t2
WHERE t.user_id = t2.user_id
  AND t.provider = t2.provider
  AND t.ctid < t2.ctid
  AND t.updated_at <= t2.updated_at;

-- Backfill provider default
UPDATE third_party_tokens SET provider = 'google' WHERE provider IS NULL;

-- Create unique index and provider identity index
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_provider ON third_party_tokens(user_id, provider);
CREATE INDEX IF NOT EXISTS idx_google_provider_identity ON third_party_tokens(provider, provider_sub);

-- SQLITE
-- Backfill provider
-- UPDATE third_party_tokens SET provider = 'google' WHERE provider IS NULL;

-- Deduplicate: keep row with max(rowid) per (user_id, provider)
-- DELETE FROM third_party_tokens
-- WHERE rowid NOT IN (
--   SELECT MAX(rowid)
--   FROM third_party_tokens
--   GROUP BY user_id, provider
-- );

-- Enforce uniqueness
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_user_provider ON third_party_tokens(user_id, provider);
-- CREATE INDEX IF NOT EXISTS idx_google_provider_identity ON third_party_tokens(provider, provider_sub);

-- End
