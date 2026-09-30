"""API Key Repository data access layer isolating SQL operations."""

import abc
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import psycopg.errors
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.database.connection import get_db_pool

logger = logging.getLogger(__name__)


@dataclass
class APIKeyRecord:
    """Represents a persisted API key record."""

    id: int
    name: str
    key_prefix: str
    key_hash: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class BaseAPIKeyRepository(abc.ABC):
    """Abstract interface for API key data access operations."""

    @abc.abstractmethod
    def create_api_key(self, name: str, key_prefix: str, key_hash: str) -> APIKeyRecord:
        """Persist a new hashed API key record."""
        pass

    @abc.abstractmethod
    def get_by_hash(self, key_hash: str) -> Optional[APIKeyRecord]:
        """Fetch API key record by its SHA-256 hash."""
        pass

    @abc.abstractmethod
    def update_last_used(self, key_id: int) -> None:
        """Update last_used_at timestamp for a given key ID."""
        pass

    @abc.abstractmethod
    def revoke_key(self, key_id: int) -> bool:
        """Deactivate and set revoked_at for a given key ID."""
        pass


class PostgresAPIKeyRepository(BaseAPIKeyRepository):
    """PostgreSQL implementation of API key repository using psycopg 3."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def create_api_key(self, name: str, key_prefix: str, key_hash: str) -> APIKeyRecord:
        query = """
            INSERT INTO api_keys (name, key_prefix, key_hash)
            VALUES (%s, %s, %s)
            RETURNING id, name, key_prefix, key_hash, is_active, created_at, last_used_at, revoked_at;
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, (name, key_prefix, key_hash))
                    row = cur.fetchone()
                    if not row:
                        raise RuntimeError("Failed to insert and retrieve API key record")
                    conn.commit()
                    return APIKeyRecord(**row)
        except psycopg.errors.UniqueViolation as e:
            raise ValueError("API key hash collision or duplicate key") from e

    def get_by_hash(self, key_hash: str) -> Optional[APIKeyRecord]:
        query = """
            SELECT id, name, key_prefix, key_hash, is_active, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE key_hash = %s;
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, (key_hash,))
                row = cur.fetchone()
                if not row:
                    return None
                return APIKeyRecord(**row)

    def update_last_used(self, key_id: int) -> None:
        query = """
            UPDATE api_keys
            SET last_used_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (key_id,))
                conn.commit()
        except Exception as e:
            logger.warning("Failed to update last_used_at for api_key id %s: %s", key_id, e)

    def revoke_key(self, key_id: int) -> bool:
        query = """
            UPDATE api_keys
            SET is_active = FALSE,
                revoked_at = CURRENT_TIMESTAMP
            WHERE id = %s AND is_active = TRUE
            RETURNING id;
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key_id,))
                row = cur.fetchone()
            conn.commit()
            return row is not None


class InMemoryAPIKeyRepository(BaseAPIKeyRepository):
    """In-memory API key repository used strictly for tests."""

    def __init__(self):
        self._records: dict[str, APIKeyRecord] = {}  # key_hash -> APIKeyRecord
        self._by_id: dict[int, APIKeyRecord] = {}
        self._counter: int = 1

    def create_api_key(self, name: str, key_prefix: str, key_hash: str) -> APIKeyRecord:
        if key_hash in self._records:
            raise ValueError("API key hash already exists in repository")

        record = APIKeyRecord(
            id=self._counter,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_used_at=None,
            revoked_at=None,
        )
        self._records[key_hash] = record
        self._by_id[self._counter] = record
        self._counter += 1
        return record

    def get_by_hash(self, key_hash: str) -> Optional[APIKeyRecord]:
        return self._records.get(key_hash)

    def update_last_used(self, key_id: int) -> None:
        record = self._by_id.get(key_id)
        if record:
            record.last_used_at = datetime.now(timezone.utc)

    def revoke_key(self, key_id: int) -> bool:
        record = self._by_id.get(key_id)
        if record and record.is_active:
            record.is_active = False
            record.revoked_at = datetime.now(timezone.utc)
            return True
        return False

    def clear(self) -> None:
        self._records.clear()
        self._by_id.clear()
        self._counter = 1


_in_memory_key_instance: Optional[InMemoryAPIKeyRepository] = None


def get_api_key_repository() -> BaseAPIKeyRepository:
    """FastAPI dependency to retrieve API Key repository.

    Uses PostgresAPIKeyRepository when a live pool is available.
    Fails explicitly if database is not configured and not in test environment.
    Tests can explicitly override this dependency with InMemoryAPIKeyRepository.
    """
    global _in_memory_key_instance
    pool = get_db_pool()
    if pool is not None:
        return PostgresAPIKeyRepository(pool)

    settings = get_settings()
    if settings.app_env.lower() in ("test", "testing"):
        if _in_memory_key_instance is None:
            _in_memory_key_instance = InMemoryAPIKeyRepository()
        return _in_memory_key_instance

    raise RuntimeError(
        "Database connection pool is not initialized and DATABASE_URL is missing. "
        "PostgreSQL is required for application runtime."
    )
