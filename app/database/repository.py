"""URL Repository data access layer isolating SQL operations."""

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


class DuplicateShortCodeError(Exception):
    """Raised when an insertion violates unique constraint on short_code."""
    pass


@dataclass
class URLRecord:
    """Represents a persisted URL record in the database."""

    id: int
    short_code: str
    original_url: str
    created_at: datetime
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0


class BaseURLRepository(abc.ABC):
    """Abstract interface for URL data access operations."""

    @abc.abstractmethod
    def create_url(self, short_code: str, original_url: str) -> URLRecord:
        """Persist a new short_code and original_url."""
        pass

    @abc.abstractmethod
    def get_by_short_code(self, short_code: str) -> Optional[URLRecord]:
        """Fetch URL record by short code."""
        pass

    @abc.abstractmethod
    def increment_access(self, short_code: str) -> None:
        """Update last_accessed_at and increment access_count."""
        pass

    @abc.abstractmethod
    def exists(self, short_code: str) -> bool:
        """Check if short code already exists in database."""
        pass


class PostgresURLRepository(BaseURLRepository):
    """PostgreSQL implementation of URL repository using psycopg 3."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def create_url(self, short_code: str, original_url: str) -> URLRecord:
        query = """
            INSERT INTO urls (short_code, original_url)
            VALUES (%s, %s)
            RETURNING id, short_code, original_url, created_at, last_accessed_at, access_count;
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, (short_code, original_url))
                    row = cur.fetchone()
                    if not row:
                        raise RuntimeError("Failed to insert and retrieve URL record")
                    conn.commit()
                    return URLRecord(**row)
        except psycopg.errors.UniqueViolation as e:
            raise DuplicateShortCodeError(f"Short code '{short_code}' already exists in database") from e

    def get_by_short_code(self, short_code: str) -> Optional[URLRecord]:
        query = """
            SELECT id, short_code, original_url, created_at, last_accessed_at, access_count
            FROM urls
            WHERE short_code = %s;
        """
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, (short_code,))
                row = cur.fetchone()
                if not row:
                    return None
                return URLRecord(**row)

    def increment_access(self, short_code: str) -> None:
        query = """
            UPDATE urls
            SET access_count = access_count + 1,
                last_accessed_at = CURRENT_TIMESTAMP
            WHERE short_code = %s;
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (short_code,))
                conn.commit()
        except Exception as e:
            logger.warning("Failed to increment access count for %s: %s", short_code, e)

    def exists(self, short_code: str) -> bool:
        query = "SELECT 1 FROM urls WHERE short_code = %s LIMIT 1;"
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, (short_code,))
                return cur.fetchone() is not None


class InMemoryURLRepository(BaseURLRepository):
    """In-memory repository used strictly for tests."""

    def __init__(self):
        self._records: dict[str, URLRecord] = {}
        self._counter: int = 1

    def create_url(self, short_code: str, original_url: str) -> URLRecord:
        if short_code in self._records:
            raise DuplicateShortCodeError(f"short_code '{short_code}' already exists")

        record = URLRecord(
            id=self._counter,
            short_code=short_code,
            original_url=original_url,
            created_at=datetime.now(timezone.utc),
            last_accessed_at=None,
            access_count=0,
        )
        self._records[short_code] = record
        self._counter += 1
        return record

    def get_by_short_code(self, short_code: str) -> Optional[URLRecord]:
        return self._records.get(short_code)

    def increment_access(self, short_code: str) -> None:
        record = self._records.get(short_code)
        if record:
            record.access_count += 1
            record.last_accessed_at = datetime.now(timezone.utc)

    def exists(self, short_code: str) -> bool:
        return short_code in self._records

    def clear(self) -> None:
        self._records.clear()
        self._counter = 1


_in_memory_instance: Optional[InMemoryURLRepository] = None


def get_repository() -> BaseURLRepository:
    """FastAPI dependency to retrieve URL repository.

    Uses PostgresURLRepository when a live pool is available.
    Fails explicitly if database is not configured and not in test environment.
    Tests can explicitly override this dependency with InMemoryURLRepository.
    """
    global _in_memory_instance
    pool = get_db_pool()
    if pool is not None:
        return PostgresURLRepository(pool)

    settings = get_settings()
    if settings.app_env.lower() in ("test", "testing"):
        if _in_memory_instance is None:
            _in_memory_instance = InMemoryURLRepository()
        return _in_memory_instance

    raise RuntimeError(
        "Database connection pool is not initialized and DATABASE_URL is missing. "
        "PostgreSQL is required for application runtime."
    )
