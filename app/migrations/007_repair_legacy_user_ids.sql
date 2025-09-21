-- Migration: Repair any remaining legacy user IDs
-- This migration converts any remaining legacy user IDs to UUIDs using the to_uuid() function logic.
-- Run this before applying referential integrity constraints.

-- ============================================================================
-- DATA REPAIR FUNCTIONS
-- ============================================================================

-- Create a function to convert legacy user IDs to UUIDs (matches app.util.ids.to_uuid)
CREATE OR REPLACE FUNCTION convert_legacy_user_id(legacy_id TEXT)
RETURNS UUID AS $$
DECLARE
    result_uuid UUID;
BEGIN
    -- Try to parse as UUID first
    BEGIN
        result_uuid := legacy_id::UUID;
        RETURN result_uuid;
    EXCEPTION
        WHEN invalid_text_representation THEN
            -- Generate deterministic UUID using the same logic as app.util.ids.to_uuid
            -- Using namespace UUID 00000000-0000-0000-0000-000000000000
            result_uuid := uuid_generate_v5('00000000-0000-0000-0000-000000000000'::UUID, legacy_id);
            RETURN result_uuid;
    END;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DATA REPAIR OPERATIONS
-- ============================================================================

-- Repair auth.sessions
UPDATE auth.sessions 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Repair auth.devices
UPDATE auth.devices 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Repair tokens.third_party_tokens
UPDATE tokens.third_party_tokens 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Repair auth.pat_tokens
UPDATE auth.pat_tokens 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Repair auth.device_sessions
UPDATE auth.device_sessions 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Repair auth.auth_identities
UPDATE auth.auth_identities 
SET user_id = convert_legacy_user_id(user_id::text)::text
WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify all user_ids are now valid UUIDs
DO $$
DECLARE
    legacy_count INTEGER;
    total_count INTEGER;
BEGIN
    -- Check auth.sessions
    SELECT COUNT(*) INTO total_count FROM auth.sessions;
    SELECT COUNT(*) INTO legacy_count
    FROM auth.sessions 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'auth.sessions: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Check auth.devices
    SELECT COUNT(*) INTO total_count FROM auth.devices;
    SELECT COUNT(*) INTO legacy_count
    FROM auth.devices 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'auth.devices: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Check tokens.third_party_tokens
    SELECT COUNT(*) INTO total_count FROM tokens.third_party_tokens;
    SELECT COUNT(*) INTO legacy_count
    FROM tokens.third_party_tokens 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'tokens.third_party_tokens: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Check auth.pat_tokens
    SELECT COUNT(*) INTO total_count FROM auth.pat_tokens;
    SELECT COUNT(*) INTO legacy_count
    FROM auth.pat_tokens 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'auth.pat_tokens: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Check auth.device_sessions
    SELECT COUNT(*) INTO total_count FROM auth.device_sessions;
    SELECT COUNT(*) INTO legacy_count
    FROM auth.device_sessions 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'auth.device_sessions: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Check auth.auth_identities
    SELECT COUNT(*) INTO total_count FROM auth.auth_identities;
    SELECT COUNT(*) INTO legacy_count
    FROM auth.auth_identities 
    WHERE length(user_id::text) < 32 OR user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';
    
    RAISE NOTICE 'auth.auth_identities: % total rows, % legacy user_ids remaining', total_count, legacy_count;
    
    -- Final check
    IF legacy_count > 0 THEN
        RAISE WARNING 'Some legacy user_ids still remain. Manual intervention may be required.';
    ELSE
        RAISE NOTICE 'All user_ids have been successfully converted to UUIDs.';
    END IF;
END $$;

-- ============================================================================
-- CLEANUP
-- ============================================================================

-- Drop the temporary function
DROP FUNCTION IF EXISTS convert_legacy_user_id(TEXT);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE auth.sessions IS 'User sessions with UUID user_ids (repaired from legacy IDs)';
COMMENT ON TABLE auth.devices IS 'User devices with UUID user_ids (repaired from legacy IDs)';
COMMENT ON TABLE tokens.third_party_tokens IS 'Third-party tokens with UUID user_ids (repaired from legacy IDs)';
COMMENT ON TABLE auth.pat_tokens IS 'Personal access tokens with UUID user_ids (repaired from legacy IDs)';
COMMENT ON TABLE auth.device_sessions IS 'Device sessions with UUID user_ids (repaired from legacy IDs)';
COMMENT ON TABLE auth.auth_identities IS 'Auth identities with UUID user_ids (repaired from legacy IDs)';
