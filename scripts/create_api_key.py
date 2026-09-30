#!/usr/bin/env python3
"""CLI utility to safely generate and store a hashed API key in PostgreSQL."""

import argparse
import os
import sys

# Ensure app root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings
from app.core.security import generate_api_key
from app.database.connection import DatabaseManager, get_db_pool
from app.database.api_key_repository import PostgresAPIKeyRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a new hashed API key for CacheShort."
    )
    parser.add_argument(
        "--name",
        type=str,
        default="admin-key",
        help="Human-readable label/name for the API key (default: admin-key)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        print("Please configure DATABASE_URL in your environment or .env file.", file=sys.stderr)
        sys.exit(1)

    try:
        DatabaseManager.initialize_pool(settings.database_url)
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    pool = get_db_pool()
    if not pool:
        print("ERROR: Connection pool is not available.", file=sys.stderr)
        sys.exit(1)

    raw_key, key_prefix, key_hash = generate_api_key()
    repo = PostgresAPIKeyRepository(pool)

    try:
        record = repo.create_api_key(name=args.name, key_prefix=key_prefix, key_hash=key_hash)
    except Exception as e:
        print(f"ERROR: Failed to insert API key record: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        DatabaseManager.close_pool()

    print("\n" + "=" * 60)
    print("SUCCESS: NEW CACHESHORT API KEY GENERATED")
    print("=" * 60)
    print(f"Key ID:     {record.id}")
    print(f"Key Name:   {record.name}")
    print(f"Key Prefix: {record.key_prefix}")
    print(f"Created At: {record.created_at.isoformat()}")
    print("-" * 60)
    print("RAW API KEY (Save this now!):")
    print(f"\n    {raw_key}\n")
    print("-" * 60)
    print("WARNING: This raw key is shown ONLY ONCE and cannot be recovered.")
    print("Only its cryptographic SHA-256 hash has been stored in PostgreSQL.")
    print("Include this header in API requests:")
    print(f"    X-API-Key: {raw_key}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
