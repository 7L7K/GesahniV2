#!/usr/bin/env python3
"""
Data Janitor - Weekly cleanup of expired tokens and old data.

This script performs weekly maintenance tasks:
- Delete expired third-party tokens older than 30 days
- Clean up old audit logs
- Remove orphaned sessions
"""

import asyncio
import logging
from datetime import datetime, UTC, timedelta
from app.db.database import get_async_db
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def cleanup_expired_tokens():
    """Delete expired third-party tokens older than 30 days."""
    logger.info("🧹 Cleaning up expired third-party tokens...")
    
    async with get_async_db() as session:
        # Delete expired tokens older than 30 days
        result = await session.execute(text("""
            DELETE FROM tokens.third_party_tokens 
            WHERE is_valid = false 
            AND updated_at < NOW() - INTERVAL '30 days'
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} expired third-party tokens")
        
        await session.commit()
        return deleted_count


async def cleanup_old_audit_logs():
    """Clean up old audit logs older than 90 days."""
    logger.info("🧹 Cleaning up old audit logs...")
    
    async with get_async_db() as session:
        # Delete audit logs older than 90 days
        result = await session.execute(text("""
            DELETE FROM audit.audit_log 
            WHERE created_at < NOW() - INTERVAL '90 days'
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} old audit log entries")
        
        await session.commit()
        return deleted_count


async def cleanup_orphaned_sessions():
    """Remove orphaned sessions (sessions without valid users)."""
    logger.info("🧹 Cleaning up orphaned sessions...")
    
    async with get_async_db() as session:
        # Delete sessions that reference non-existent users
        result = await session.execute(text("""
            DELETE FROM auth.sessions 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} orphaned sessions")
        
        await session.commit()
        return deleted_count


async def cleanup_orphaned_devices():
    """Remove orphaned devices (devices without valid users)."""
    logger.info("🧹 Cleaning up orphaned devices...")
    
    async with get_async_db() as session:
        # Delete devices that reference non-existent users
        result = await session.execute(text("""
            DELETE FROM auth.devices 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} orphaned devices")
        
        await session.commit()
        return deleted_count


async def cleanup_orphaned_pat_tokens():
    """Remove orphaned PAT tokens (tokens without valid users)."""
    logger.info("🧹 Cleaning up orphaned PAT tokens...")
    
    async with get_async_db() as session:
        # Delete PAT tokens that reference non-existent users
        result = await session.execute(text("""
            DELETE FROM auth.pat_tokens 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} orphaned PAT tokens")
        
        await session.commit()
        return deleted_count


async def cleanup_orphaned_third_party_tokens():
    """Remove orphaned third-party tokens (tokens without valid users)."""
    logger.info("🧹 Cleaning up orphaned third-party tokens...")
    
    async with get_async_db() as session:
        # Delete third-party tokens that reference non-existent users
        result = await session.execute(text("""
            DELETE FROM tokens.third_party_tokens 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        
        deleted_count = result.rowcount
        logger.info(f"✅ Deleted {deleted_count} orphaned third-party tokens")
        
        await session.commit()
        return deleted_count


async def get_cleanup_statistics():
    """Get statistics about data that could be cleaned up."""
    logger.info("📊 Gathering cleanup statistics...")
    
    async with get_async_db() as session:
        # Count expired tokens
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM tokens.third_party_tokens 
            WHERE is_valid = false 
            AND updated_at < NOW() - INTERVAL '30 days'
        """))
        expired_tokens = result.scalar()
        
        # Count old audit logs
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM audit.audit_log 
            WHERE created_at < NOW() - INTERVAL '90 days'
        """))
        old_audit_logs = result.scalar()
        
        # Count orphaned sessions
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM auth.sessions 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        orphaned_sessions = result.scalar()
        
        # Count orphaned devices
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM auth.devices 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        orphaned_devices = result.scalar()
        
        # Count orphaned PAT tokens
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM auth.pat_tokens 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        orphaned_pat_tokens = result.scalar()
        
        # Count orphaned third-party tokens
        result = await session.execute(text("""
            SELECT COUNT(*) as count
            FROM tokens.third_party_tokens 
            WHERE user_id NOT IN (SELECT id FROM auth.users)
        """))
        orphaned_third_party_tokens = result.scalar()
        
        stats = {
            "expired_tokens": expired_tokens,
            "old_audit_logs": old_audit_logs,
            "orphaned_sessions": orphaned_sessions,
            "orphaned_devices": orphaned_devices,
            "orphaned_pat_tokens": orphaned_pat_tokens,
            "orphaned_third_party_tokens": orphaned_third_party_tokens,
            "total_cleanup_candidates": (
                expired_tokens + old_audit_logs + orphaned_sessions + 
                orphaned_devices + orphaned_pat_tokens + orphaned_third_party_tokens
            )
        }
        
        logger.info(f"📊 Cleanup statistics: {stats}")
        return stats


async def main():
    """Main function to run the data janitor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data Janitor - Weekly cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be cleaned up without actually doing it")
    parser.add_argument("--stats-only", action="store_true", help="Only show statistics, don't perform cleanup")
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Data Janitor...")
    
    if args.stats_only:
        # Only show statistics
        stats = await get_cleanup_statistics()
        print("\n" + "="*60)
        print("DATA JANITOR STATISTICS")
        print("="*60)
        for key, value in stats.items():
            print(f"{key}: {value}")
        return
    
    if args.dry_run:
        # Show what would be cleaned up
        stats = await get_cleanup_statistics()
        print("\n" + "="*60)
        print("DATA JANITOR DRY RUN")
        print("="*60)
        print("The following data would be cleaned up:")
        for key, value in stats.items():
            if key != "total_cleanup_candidates":
                print(f"  {key}: {value}")
        print(f"\nTotal records to be cleaned: {stats['total_cleanup_candidates']}")
        return
    
    # Perform actual cleanup
    total_cleaned = 0
    
    try:
        # Clean up expired tokens
        cleaned = await cleanup_expired_tokens()
        total_cleaned += cleaned
        
        # Clean up old audit logs
        cleaned = await cleanup_old_audit_logs()
        total_cleaned += cleaned
        
        # Clean up orphaned data
        cleaned = await cleanup_orphaned_sessions()
        total_cleaned += cleaned
        
        cleaned = await cleanup_orphaned_devices()
        total_cleaned += cleaned
        
        cleaned = await cleanup_orphaned_pat_tokens()
        total_cleaned += cleaned
        
        cleaned = await cleanup_orphaned_third_party_tokens()
        total_cleaned += cleaned
        
        logger.info(f"🎉 Data janitor completed successfully!")
        logger.info(f"📊 Total records cleaned: {total_cleaned}")
        
    except Exception as e:
        logger.error(f"❌ Data janitor failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
