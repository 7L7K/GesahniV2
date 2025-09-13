#!/usr/bin/env python3
"""
Database Migration Phase 2 Verification Script

Checks the following requirements:
1. Extensions: citext, pgcrypto, uuid-ossp exist
2. Schemas: auth, audit, storage, users, tokens, care, chat, music exist
3. Tables: auth.device_sessions, music.music_states, storage.ledger, tokens.third_party_tokens exist
4. Critical deltas:
   - audit.audit_log.session_id is TEXT and FK → auth.device_sessions.sid
   - storage.ledger has UNIQUE (user_id, idempotency_key)
5. Concurrent indexes are valid
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Tuple, Optional

def get_db_connection():
    """Get database connection from environment or default"""
    db_url = os.getenv('DATABASE_URL', 'postgresql://app:app_pw@localhost:5432/gesahni')

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True  # Enable autocommit to avoid transaction issues
        return conn
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        print("Make sure PostgreSQL is running and DATABASE_URL is set correctly")
        return None

def check_extensions(conn) -> Tuple[bool, List[str]]:
    """Check if required extensions exist"""
    required_extensions = ['citext', 'pgcrypto', 'uuid-ossp']
    existing_extensions = []

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT extname FROM pg_extension
                WHERE extname IN %s
                ORDER BY extname
            """, (tuple(required_extensions),))
            existing_extensions = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error checking extensions: {e}")
        return False, []

    missing = [ext for ext in required_extensions if ext not in existing_extensions]
    return len(missing) == 0, missing

def check_schemas(conn) -> Tuple[bool, List[str]]:
    """Check if required schemas exist"""
    required_schemas = ['auth', 'audit', 'storage', 'users', 'tokens', 'care', 'chat', 'music']
    existing_schemas = []

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name IN %s
                ORDER BY schema_name
            """, (tuple(required_schemas),))
            existing_schemas = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error checking schemas: {e}")
        return False, []

    missing = [schema for schema in required_schemas if schema not in existing_schemas]
    return len(missing) == 0, missing

def check_tables(conn) -> Tuple[bool, List[str]]:
    """Check if required tables exist"""
    required_tables = [
        ('auth', 'device_sessions'),
        ('music', 'music_states'),
        ('storage', 'ledger'),
        ('tokens', 'third_party_tokens')
    ]
    missing_tables = []

    try:
        with conn.cursor() as cur:
            for schema, table in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                """, (schema, table))
                exists = cur.fetchone()[0]
                if not exists:
                    missing_tables.append(f"{schema}.{table}")
    except Exception as e:
        print(f"Error checking tables: {e}")
        return False, []

    return len(missing_tables) == 0, missing_tables

def check_audit_log_fk(conn) -> Tuple[bool, Dict]:
    """Check audit.audit_log.session_id is TEXT and FK → auth.device_sessions.sid"""
    issues = {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check column type
            cur.execute("""
                SELECT data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'audit' AND table_name = 'audit_log' AND column_name = 'session_id'
            """)
            col_info = cur.fetchone()

            if not col_info:
                issues['missing_column'] = 'audit.audit_log.session_id column does not exist'
                return False, issues

            if col_info['data_type'] != 'text':
                issues['wrong_type'] = f"session_id is {col_info['data_type']}, expected text"

            # Check foreign key constraint using pg_constraint
            cur.execute("""
                SELECT
                    con.conname as constraint_name,
                    con.conrelid::regclass as table_name,
                    ta.attname as column_name,
                    con.confrelid::regclass as foreign_table_name,
                    fa.attname as foreign_column_name
                FROM pg_constraint con
                JOIN pg_attribute ta ON ta.attrelid = con.conrelid AND ta.attnum = con.conkey[1]
                JOIN pg_attribute fa ON fa.attrelid = con.confrelid AND fa.attnum = con.confkey[1]
                WHERE con.contype = 'f'
                  AND con.conrelid = 'audit.audit_log'::regclass
                  AND ta.attname = 'session_id'
            """)
            fk_info = cur.fetchone()

            if not fk_info:
                issues['missing_fk'] = 'No foreign key constraint found on audit.audit_log.session_id'
            elif str(fk_info['foreign_table_name']) != 'auth.device_sessions' or fk_info['foreign_column_name'] != 'sid':
                issues['wrong_fk_target'] = f"FK points to {fk_info['foreign_table_name']}.{fk_info['foreign_column_name']}, expected auth.device_sessions.sid"

    except Exception as e:
        issues['error'] = f"Error checking audit log FK: {e}"

    return len(issues) == 0, issues

def check_ledger_unique_constraint(conn) -> Tuple[bool, Dict]:
    """Check storage.ledger has UNIQUE (user_id, idempotency_key)"""
    issues = {}
    constraints = []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if table exists first
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'storage' AND table_name = 'ledger'
                )
            """)
            result = cur.fetchone()
            table_exists = result['exists'] if result else False

            if not table_exists:
                issues['missing_table'] = 'storage.ledger table does not exist'
                return False, issues

            # Check for unique constraint using pg_constraint
            cur.execute("""
                SELECT
                    con.conname as constraint_name,
                    array_agg(att.attname ORDER BY array_position(con.conkey, att.attnum)) as columns
                FROM pg_constraint con
                JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
                WHERE con.contype = 'u'
                  AND con.conrelid = 'storage.ledger'::regclass
                GROUP BY con.conname
            """)
            constraints = cur.fetchall()

            found_unique = False
            for constraint in constraints:
                # constraint['columns'] is already a list from the array_agg
                columns = ','.join(constraint['columns'])
                if columns == 'user_id,idempotency_key':
                    found_unique = True
                    break

            if not found_unique:
                issues['missing_unique'] = 'No UNIQUE constraint found on (user_id, idempotency_key)'
                if constraints:
                    issues['existing_constraints'] = [','.join(c['columns']) for c in constraints]

    except Exception as e:
        issues['error'] = f"Error checking ledger unique constraint: {str(e)} - constraints: {constraints}"

    return len(issues) == 0, issues

def check_concurrent_indexes(conn) -> Tuple[bool, Dict]:
    """Check concurrent indexes are valid"""
    issues = {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all indexes with their validity status
            cur.execute("""
                SELECT
                    schemaname,
                    tablename,
                    indexname,
                    indexdef,
                    indisvalid,
                    indisready,
                    indisunique
                FROM pg_indexes i
                JOIN pg_class c ON i.indexname = c.relname
                JOIN pg_index idx ON c.oid = idx.indexrelid
                WHERE i.schemaname IN ('auth', 'audit', 'storage', 'users', 'tokens', 'care', 'chat', 'music')
                ORDER BY schemaname, tablename, indexname
            """)
            indexes = cur.fetchall()

            invalid_indexes = []
            for idx in indexes:
                if not idx['indisvalid']:
                    invalid_indexes.append(f"{idx['schemaname']}.{idx['tablename']}.{idx['indexname']}")

            if invalid_indexes:
                issues['invalid_indexes'] = invalid_indexes

    except Exception as e:
        issues['error'] = f"Error checking concurrent indexes: {e}"

    return len(issues) == 0, issues

def main():
    """Main verification function"""
    print("🔍 Database Migration Phase 2 Verification")
    print("=" * 50)

    conn = get_db_connection()
    if not conn:
        return False

    all_good = True

    try:
        # 1. Check extensions
        print("\n1. Checking PostgreSQL extensions...")
        ext_ok, missing_ext = check_extensions(conn)
        if ext_ok:
            print("✅ All required extensions exist: citext, pgcrypto, uuid-ossp")
        else:
            print(f"❌ Missing extensions: {', '.join(missing_ext)}")
            all_good = False

        # 2. Check schemas
        print("\n2. Checking schemas...")
        schema_ok, missing_schemas = check_schemas(conn)
        if schema_ok:
            print("✅ All required schemas exist: auth, audit, storage, users, tokens, care, chat, music")
        else:
            print(f"❌ Missing schemas: {', '.join(missing_schemas)}")
            all_good = False

        # 3. Check tables
        print("\n3. Checking tables...")
        table_ok, missing_tables = check_tables(conn)
        if table_ok:
            print("✅ All required tables exist: auth.device_sessions, music.music_states, storage.ledger, tokens.third_party_tokens")
        else:
            print(f"❌ Missing tables: {', '.join(missing_tables)}")
            all_good = False

        # 4. Check audit log FK
        print("\n4. Checking audit.audit_log.session_id FK...")
        audit_ok, audit_issues = check_audit_log_fk(conn)
        if audit_ok:
            print("✅ audit.audit_log.session_id is TEXT and properly FK → auth.device_sessions.sid")
        else:
            print("❌ Issues with audit.audit_log.session_id:")
            for issue, detail in audit_issues.items():
                print(f"   - {issue}: {detail}")
            all_good = False

        # 5. Check ledger unique constraint
        print("\n5. Checking storage.ledger unique constraint...")
        ledger_ok, ledger_issues = check_ledger_unique_constraint(conn)
        if ledger_ok:
            print("✅ storage.ledger has UNIQUE (user_id, idempotency_key)")
        else:
            print("❌ Issues with storage.ledger unique constraint:")
            for issue, detail in ledger_issues.items():
                print(f"   - {issue}: {detail}")
            all_good = False

        # 6. Check concurrent indexes
        print("\n6. Checking concurrent indexes...")
        index_ok, index_issues = check_concurrent_indexes(conn)
        if index_ok:
            print("✅ All concurrent indexes are valid")
        else:
            print("❌ Issues with concurrent indexes:")
            for issue, detail in index_issues.items():
                print(f"   - {issue}: {detail}")
            all_good = False

    finally:
        conn.close()

    print("\n" + "=" * 50)
    if all_good:
        print("🎉 ALL CHECKS PASSED - DB Migrations Phase 2 Complete!")
        return True
    else:
        print("⚠️  SOME CHECKS FAILED - Additional migrations needed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

