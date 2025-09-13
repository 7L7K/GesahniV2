-- Phase 2 Migration: Add missing extensions, schemas, tables, and constraints
-- This script completes the DB Migrations Phase 2 requirements

-- 1. Create missing extensions
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2. Create missing schemas
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS chat;

-- 3. Create missing tables

-- auth.device_sessions table
CREATE TABLE IF NOT EXISTS auth.device_sessions (
    sid TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    device_name VARCHAR(200),
    ua_hash VARCHAR(128) NOT NULL,
    ip_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    UNIQUE(user_id, ua_hash, ip_hash)
);

-- music.music_states table
CREATE TABLE IF NOT EXISTS music.music_states (
    session_id UUID PRIMARY KEY REFERENCES music.music_sessions(session_id) ON DELETE CASCADE,
    state JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- storage.ledger table with unique constraint
CREATE TABLE IF NOT EXISTS storage.ledger (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    operation VARCHAR(100) NOT NULL,
    amount DECIMAL(10,2),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, idempotency_key)
);

-- 4. Modify audit.audit_log.session_id to be TEXT and add FK
-- First, add the new column
ALTER TABLE audit.audit_log ADD COLUMN IF NOT EXISTS session_id_text TEXT;

-- Copy data from old UUID column to new TEXT column (converting to text)
UPDATE audit.audit_log SET session_id_text = session_id::TEXT WHERE session_id IS NOT NULL;

-- Drop the old FK constraint if it exists
ALTER TABLE audit.audit_log DROP CONSTRAINT IF EXISTS audit_log_session_id_fkey;

-- Drop the old column
ALTER TABLE audit.audit_log DROP COLUMN IF EXISTS session_id;

-- Rename the new column to session_id
ALTER TABLE audit.audit_log RENAME COLUMN session_id_text TO session_id;

-- Add the new foreign key constraint to auth.device_sessions.sid
ALTER TABLE audit.audit_log ADD CONSTRAINT audit_log_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES auth.device_sessions(sid) ON DELETE SET NULL;

-- 5. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_audit_log_session_id ON audit.audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_device_sessions_user_id ON auth.device_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_device_sessions_last_seen ON auth.device_sessions(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_music_states_updated_at ON music.music_states(updated_at);
CREATE INDEX IF NOT EXISTS idx_ledger_user_created ON storage.ledger(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_idempotency ON storage.ledger(idempotency_key);

-- 6. Grant permissions (using the app user we created)
GRANT USAGE ON SCHEMA storage TO app;
GRANT USAGE ON SCHEMA chat TO app;
GRANT ALL ON ALL TABLES IN SCHEMA storage TO app;
GRANT ALL ON ALL TABLES IN SCHEMA chat TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA storage TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA chat TO app;

-- Also grant on existing schemas for completeness
GRANT USAGE ON SCHEMA auth TO app;
GRANT USAGE ON SCHEMA audit TO app;
GRANT USAGE ON SCHEMA users TO app;
GRANT USAGE ON SCHEMA tokens TO app;
GRANT USAGE ON SCHEMA care TO app;
GRANT USAGE ON SCHEMA music TO app;
GRANT ALL ON ALL TABLES IN SCHEMA auth TO app;
GRANT ALL ON ALL TABLES IN SCHEMA audit TO app;
GRANT ALL ON ALL TABLES IN SCHEMA users TO app;
GRANT ALL ON ALL TABLES IN SCHEMA tokens TO app;
GRANT ALL ON ALL TABLES IN SCHEMA care TO app;
GRANT ALL ON ALL TABLES IN SCHEMA music TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA audit TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA users TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA tokens TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA care TO app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA music TO app;
