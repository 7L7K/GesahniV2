-- Migration: Fix legacy user IDs in database tables
-- This migration addresses the issue where legacy usernames (9-char handles) 
-- were being stored directly in UUID columns, causing database errors.

-- First, let's check if there are any sessions with non-UUID user_ids
-- (This is a diagnostic query - it should return 0 rows after the fix)
SELECT 'sessions_with_legacy_ids' as table_name, COUNT(*) as count
FROM auth.sessions 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'sessions_with_short_ids' as table_name, COUNT(*) as count
FROM auth.sessions 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check third_party_tokens table for similar issues
SELECT 'tokens_with_legacy_ids' as table_name, COUNT(*) as count
FROM tokens.third_party_tokens 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'tokens_with_short_ids' as table_name, COUNT(*) as count
FROM tokens.third_party_tokens 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check auth_identities table
SELECT 'identities_with_legacy_ids' as table_name, COUNT(*) as count
FROM auth.auth_identities 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'identities_with_short_ids' as table_name, COUNT(*) as count
FROM auth.auth_identities 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check pat_tokens table
SELECT 'pat_tokens_with_legacy_ids' as table_name, COUNT(*) as count
FROM auth.pat_tokens 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'pat_tokens_with_short_ids' as table_name, COUNT(*) as count
FROM auth.pat_tokens 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check device_sessions table
SELECT 'device_sessions_with_legacy_ids' as table_name, COUNT(*) as count
FROM auth.device_sessions 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'device_sessions_with_short_ids' as table_name, COUNT(*) as count
FROM auth.device_sessions 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check music_tokens table
SELECT 'music_tokens_with_legacy_ids' as table_name, COUNT(*) as count
FROM music.music_tokens 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'music_tokens_with_short_ids' as table_name, COUNT(*) as count
FROM music.music_tokens 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check chat_messages table
SELECT 'chat_messages_with_legacy_ids' as table_name, COUNT(*) as count
FROM chat.chat_messages 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'chat_messages_with_short_ids' as table_name, COUNT(*) as count
FROM chat.chat_messages 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check user_stats table
SELECT 'user_stats_with_legacy_ids' as table_name, COUNT(*) as count
FROM users.user_stats 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'user_stats_with_short_ids' as table_name, COUNT(*) as count
FROM users.user_stats 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check storage.ledger table
SELECT 'ledger_with_legacy_ids' as table_name, COUNT(*) as count
FROM storage.ledger 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'ledger_with_short_ids' as table_name, COUNT(*) as count
FROM storage.ledger 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check user_data.notes table
SELECT 'notes_with_legacy_ids' as table_name, COUNT(*) as count
FROM user_data.notes 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'notes_with_short_ids' as table_name, COUNT(*) as count
FROM user_data.notes 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Check audit.audit_log table
SELECT 'audit_log_with_legacy_ids' as table_name, COUNT(*) as count
FROM audit.audit_log 
WHERE length(user_id::text) < 32
UNION ALL
SELECT 'audit_log_with_short_ids' as table_name, COUNT(*) as count
FROM audit.audit_log 
WHERE user_id::text ~ '^[A-Za-z0-9_-]{1,12}$';

-- Note: This migration is primarily diagnostic. The actual fix is in the application code
-- where we now convert legacy user IDs to UUIDs using the to_uuid() function before
-- performing database operations. This ensures that all database queries use proper UUIDs
-- regardless of whether the input is a legacy username or a proper UUID.
