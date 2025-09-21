-- Migration: Add referential integrity constraints and indexes
-- This migration adds foreign key constraints, NOT NULL constraints, and indexes
-- to ensure data integrity and prevent legacy ID issues.

-- ============================================================================
-- FOREIGN KEY CONSTRAINTS
-- ============================================================================

-- Add foreign key constraints for auth.sessions
ALTER TABLE auth.sessions 
ADD CONSTRAINT fk_sessions_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Add foreign key constraints for auth.devices
ALTER TABLE auth.devices 
ADD CONSTRAINT fk_devices_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Add foreign key constraints for tokens.third_party_tokens
ALTER TABLE tokens.third_party_tokens 
ADD CONSTRAINT fk_third_party_tokens_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Add foreign key constraints for auth.pat_tokens
ALTER TABLE auth.pat_tokens 
ADD CONSTRAINT fk_pat_tokens_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Add foreign key constraints for auth.device_sessions
ALTER TABLE auth.device_sessions 
ADD CONSTRAINT fk_device_sessions_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Add foreign key constraints for auth.auth_identities
ALTER TABLE auth.auth_identities 
ADD CONSTRAINT fk_auth_identities_user_id 
FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- ============================================================================
-- NOT NULL CONSTRAINTS
-- ============================================================================

-- Ensure user_id columns are NOT NULL
ALTER TABLE auth.sessions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE auth.devices ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE tokens.third_party_tokens ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE auth.pat_tokens ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE auth.device_sessions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE auth.auth_identities ALTER COLUMN user_id SET NOT NULL;

-- Ensure provider is NOT NULL for third_party_tokens
ALTER TABLE tokens.third_party_tokens ALTER COLUMN provider SET NOT NULL;

-- Ensure is_valid is NOT NULL for third_party_tokens
ALTER TABLE tokens.third_party_tokens ALTER COLUMN is_valid SET NOT NULL;

-- ============================================================================
-- UNIQUE CONSTRAINTS
-- ============================================================================

-- Ensure unique alias constraints (if not already present)
-- Note: These might already exist, so we use IF NOT EXISTS pattern
DO $$
BEGIN
    -- Add unique constraint on alias if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uk_user_aliases_alias'
    ) THEN
        ALTER TABLE auth.user_aliases 
        ADD CONSTRAINT uk_user_aliases_alias UNIQUE (alias);
    END IF;
    
    -- Add unique constraint on (user_uuid, alias) if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uk_user_aliases_user_uuid_alias'
    ) THEN
        ALTER TABLE auth.user_aliases 
        ADD CONSTRAINT uk_user_aliases_user_uuid_alias UNIQUE (user_uuid, alias);
    END IF;
END $$;

-- ============================================================================
-- INDEXES FOR PERFORMANCE AND MONITORING
-- ============================================================================

-- Index for finding potential legacy IDs during rollout (temporary)
CREATE INDEX IF NOT EXISTS idx_sessions_maybe_legacy
ON auth.sessions ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Index for finding potential legacy IDs in devices
CREATE INDEX IF NOT EXISTS idx_devices_maybe_legacy
ON auth.devices ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Index for finding potential legacy IDs in third_party_tokens
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_maybe_legacy
ON tokens.third_party_tokens ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Index for finding potential legacy IDs in pat_tokens
CREATE INDEX IF NOT EXISTS idx_pat_tokens_maybe_legacy
ON auth.pat_tokens ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Index for finding potential legacy IDs in device_sessions
CREATE INDEX IF NOT EXISTS idx_device_sessions_maybe_legacy
ON auth.device_sessions ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Index for finding potential legacy IDs in auth_identities
CREATE INDEX IF NOT EXISTS idx_auth_identities_maybe_legacy
ON auth.auth_identities ((user_id::text))
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================

-- Index for user_id lookups in sessions
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON auth.sessions (user_id);

-- Index for user_id lookups in devices
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON auth.devices (user_id);

-- Index for user_id lookups in third_party_tokens
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_user_id ON tokens.third_party_tokens (user_id);

-- Index for user_id lookups in pat_tokens
CREATE INDEX IF NOT EXISTS idx_pat_tokens_user_id ON auth.pat_tokens (user_id);

-- Index for user_id lookups in device_sessions
CREATE INDEX IF NOT EXISTS idx_device_sessions_user_id ON auth.device_sessions (user_id);

-- Index for user_id lookups in auth_identities
CREATE INDEX IF NOT EXISTS idx_auth_identities_user_id ON auth.auth_identities (user_id);

-- Index for provider lookups in third_party_tokens
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_provider ON tokens.third_party_tokens (provider);

-- Index for is_valid lookups in third_party_tokens
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_is_valid ON tokens.third_party_tokens (is_valid);

-- Composite index for user_id + provider lookups
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_user_provider 
ON tokens.third_party_tokens (user_id, provider);

-- Composite index for user_id + is_valid lookups
CREATE INDEX IF NOT EXISTS idx_third_party_tokens_user_valid 
ON tokens.third_party_tokens (user_id, is_valid);

-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- Verify no legacy IDs exist before applying constraints
DO $$
DECLARE
    legacy_count INTEGER;
BEGIN
    -- Check for legacy IDs in sessions
    SELECT COUNT(*) INTO legacy_count
    FROM auth.sessions 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in auth.sessions. Run data repair first.', legacy_count;
    END IF;
    
    -- Check for legacy IDs in devices
    SELECT COUNT(*) INTO legacy_count
    FROM auth.devices 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in auth.devices. Run data repair first.', legacy_count;
    END IF;
    
    -- Check for legacy IDs in third_party_tokens
    SELECT COUNT(*) INTO legacy_count
    FROM tokens.third_party_tokens 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in tokens.third_party_tokens. Run data repair first.', legacy_count;
    END IF;
    
    -- Check for legacy IDs in pat_tokens
    SELECT COUNT(*) INTO legacy_count
    FROM auth.pat_tokens 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in auth.pat_tokens. Run data repair first.', legacy_count;
    END IF;
    
    -- Check for legacy IDs in device_sessions
    SELECT COUNT(*) INTO legacy_count
    FROM auth.device_sessions 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in auth.device_sessions. Run data repair first.', legacy_count;
    END IF;
    
    -- Check for legacy IDs in auth_identities
    SELECT COUNT(*) INTO legacy_count
    FROM auth.auth_identities 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    IF legacy_count > 0 THEN
        RAISE EXCEPTION 'Found % legacy user_ids in auth.auth_identities. Run data repair first.', legacy_count;
    END IF;
    
    RAISE NOTICE 'All user_ids are valid UUIDs. Proceeding with constraint creation.';
END $$;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON CONSTRAINT fk_sessions_user_id ON auth.sessions IS 'Foreign key to auth.users with CASCADE delete';
COMMENT ON CONSTRAINT fk_devices_user_id ON auth.devices IS 'Foreign key to auth.users with CASCADE delete';
COMMENT ON CONSTRAINT fk_third_party_tokens_user_id ON tokens.third_party_tokens IS 'Foreign key to auth.users with CASCADE delete';
COMMENT ON CONSTRAINT fk_pat_tokens_user_id ON auth.pat_tokens IS 'Foreign key to auth.users with CASCADE delete';
COMMENT ON CONSTRAINT fk_device_sessions_user_id ON auth.device_sessions IS 'Foreign key to auth.users with CASCADE delete';
COMMENT ON CONSTRAINT fk_auth_identities_user_id ON auth.auth_identities IS 'Foreign key to auth.users with CASCADE delete';

COMMENT ON INDEX idx_sessions_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
COMMENT ON INDEX idx_devices_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
COMMENT ON INDEX idx_third_party_tokens_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
COMMENT ON INDEX idx_pat_tokens_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
COMMENT ON INDEX idx_device_sessions_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
COMMENT ON INDEX idx_auth_identities_maybe_legacy IS 'Temporary index for finding legacy user_ids during rollout';
