#!/usr/bin/env python3
"""
Migration script to move Spotify tokens from JSON files to the unified database.

This script:
1. Scans data/spotify_tokens/*.json files
2. Migrates tokens to the third_party_tokens table
3. Validates token data
4. Provides rollback capability
5. Logs migration progress and any issues

Usage:
    python scripts/migrate_spotify_tokens.py --dry-run  # Preview migration
    python scripts/migrate_spotify_tokens.py --migrate  # Perform migration
    python scripts/migrate_spotify_tokens.py --rollback # Rollback migration
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth_store_tokens import TokenDAO, upsert_token
from app.models.third_party_tokens import ThirdPartyToken

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
SPOTIFY_TOKENS_DIR = Path(os.getenv("SPOTIFY_TOKENS_DIR", "data/spotify_tokens"))
BACKUP_SUFFIX = ".migration_backup"
MIGRATION_LOG_FILE = "spotify_migration.log"


class SpotifyTokenMigrator:
    """Handles migration of Spotify tokens from JSON files to database."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.token_dao = TokenDAO()
        self.migration_stats = {
            "files_processed": 0,
            "tokens_migrated": 0,
            "tokens_skipped": 0,
            "errors": 0,
            "backups_created": 0,
        }

    def setup_logging_to_file(self) -> None:
        """Set up logging to both console and file."""
        file_handler = logging.FileHandler(MIGRATION_LOG_FILE)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

    def find_spotify_token_files(self) -> list[Path]:
        """Find all Spotify token JSON files."""
        if not SPOTIFY_TOKENS_DIR.exists():
            logger.warning(f"Spotify tokens directory not found: {SPOTIFY_TOKENS_DIR}")
            return []

        token_files = list(SPOTIFY_TOKENS_DIR.glob("*.json"))
        logger.info(f"Found {len(token_files)} potential token files")
        return token_files

    def parse_token_file(self, file_path: Path) -> Optional[dict[str, Any]]:
        """Parse a single token JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate required fields
            if not isinstance(data, dict):
                logger.error(f"Invalid JSON structure in {file_path}")
                return None

            required_fields = ["access_token", "refresh_token", "expires_at"]
            if not all(field in data for field in required_fields):
                logger.error(
                    f"Missing required fields in {file_path}: {required_fields}"
                )
                return None

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading {file_path}: {e}")
            return None

    def create_token_from_json(
        self, user_id: str, json_data: dict[str, Any]
    ) -> Optional[ThirdPartyToken]:
        """Create a ThirdPartyToken from JSON data."""
        try:
            # Extract user_id from filename (remove .json extension)
            if not user_id:
                logger.error("Empty user_id provided")
                return None

            # Validate token data
            access_token = json_data.get("access_token", "").strip()
            refresh_token = json_data.get("refresh_token", "").strip()
            expires_at = json_data.get("expires_at", 0)
            scope = json_data.get("scope")

            if not access_token:
                logger.error(f"Empty access_token for user {user_id}")
                return None

            if not refresh_token:
                logger.error(f"Empty refresh_token for user {user_id}")
                return None

            if not isinstance(expires_at, (int, float)) or expires_at <= 0:
                logger.error(f"Invalid expires_at for user {user_id}: {expires_at}")
                return None

            # Create token object
            token = ThirdPartyToken(
                user_id=user_id,
                provider="spotify",
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=int(expires_at),
                created_at=int(time.time()),  # Use current time as creation time
                updated_at=int(time.time()),
            )

            return token

        except Exception as e:
            logger.error(f"Failed to create token object for user {user_id}: {e}")
            return None

    def create_backup(self, file_path: Path) -> bool:
        """Create a backup of the original file."""
        if self.dry_run:
            return True

        backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        try:
            with open(file_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
            self.migration_stats["backups_created"] += 1
            logger.info(f"Created backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create backup for {file_path}: {e}")
            return False

    async def migrate_token_file(self, file_path: Path) -> bool:
        """Migrate a single token file."""
        self.migration_stats["files_processed"] += 1

        # Extract user_id from filename
        user_id = file_path.stem  # Remove .json extension
        if not user_id:
            logger.error(f"Could not extract user_id from filename: {file_path}")
            self.migration_stats["errors"] += 1
            return False

        # Parse JSON file
        json_data = self.parse_token_file(file_path)
        if not json_data:
            self.migration_stats["errors"] += 1
            return False

        # Create token object
        token = self.create_token_from_json(user_id, json_data)
        if not token:
            self.migration_stats["errors"] += 1
            return False

        # Check if token already exists in database
        existing_token = await self.token_dao.get_token(user_id, "spotify")
        if existing_token:
            logger.info(f"Token already exists for user {user_id}, skipping")
            self.migration_stats["tokens_skipped"] += 1
            return True

        if self.dry_run:
            logger.info(f"DRY RUN: Would migrate token for user {user_id}")
            self.migration_stats["tokens_migrated"] += 1
            return True

        # Create backup before migration
        if not self.create_backup(file_path):
            logger.error(f"Failed to create backup for {file_path}, skipping migration")
            self.migration_stats["errors"] += 1
            return False

        # Migrate to database
        success = await self.token_dao.upsert_token(token)
        if success:
            logger.info(f"Successfully migrated token for user {user_id}")
            self.migration_stats["tokens_migrated"] += 1
            return True
        else:
            logger.error(f"Failed to migrate token for user {user_id}")
            self.migration_stats["errors"] += 1
            return False

    async def run_migration(self) -> bool:
        """Run the complete migration process."""
        logger.info("Starting Spotify token migration")
        logger.info(f"Dry run: {self.dry_run}")

        if self.dry_run:
            logger.info("DRY RUN MODE - No actual changes will be made")

        # Find all token files
        token_files = self.find_spotify_token_files()
        if not token_files:
            logger.warning("No token files found to migrate")
            return True

        # Process each file
        success_count = 0
        for file_path in token_files:
            if await self.migrate_token_file(file_path):
                success_count += 1

        # Log final statistics
        logger.info("Migration completed")
        logger.info(f"Files processed: {self.migration_stats['files_processed']}")
        logger.info(f"Tokens migrated: {self.migration_stats['tokens_migrated']}")
        logger.info(f"Tokens skipped: {self.migration_stats['tokens_skipped']}")
        logger.info(f"Errors: {self.migration_stats['errors']}")
        logger.info(f"Backups created: {self.migration_stats['backups_created']}")

        success_rate = success_count / len(token_files) if token_files else 0
        logger.info(f"Success rate: {success_rate:.2%}")

        return self.migration_stats["errors"] == 0

    async def rollback_migration(self) -> bool:
        """Rollback the migration by removing migrated tokens."""
        if self.dry_run:
            logger.info("DRY RUN: Would remove all Spotify tokens from database")
            return True

        logger.info("Starting migration rollback")

        try:
            # Remove all Spotify tokens from database
            with sqlite3.connect(self.token_dao.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM third_party_tokens
                    WHERE provider = 'spotify'
                """
                )
                deleted_count = cursor.rowcount
                conn.commit()

            logger.info(f"Removed {deleted_count} Spotify tokens from database")

            # Restore backup files (optional - user can do this manually)
            logger.info(
                "Note: Original JSON files are backed up with suffix '{BACKUP_SUFFIX}'"
            )
            logger.info("You can manually restore them if needed")

            return True

        except Exception as e:
            logger.error(f"Failed to rollback migration: {e}")
            return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate Spotify tokens from JSON to database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )
    parser.add_argument(
        "--migrate", action="store_true", help="Perform the actual migration"
    )
    parser.add_argument(
        "--rollback", action="store_true", help="Rollback the migration"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    actions = [args.dry_run, args.migrate, args.rollback]
    if sum(actions) != 1:
        parser.error(
            "Exactly one of --dry-run, --migrate, or --rollback must be specified"
        )

    # Create migrator
    dry_run = args.dry_run
    migrator = SpotifyTokenMigrator(dry_run=dry_run)
    migrator.setup_logging_to_file()

    try:
        if args.rollback:
            success = await migrator.rollback_migration()
        else:
            success = await migrator.run_migration()

        if success:
            logger.info("Operation completed successfully")
            return 0
        else:
            logger.error("Operation failed")
            return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
