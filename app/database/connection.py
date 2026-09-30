"""Database connection management and pooling using psycopg 3."""

import logging
from typing import Optional
from psycopg_pool import ConnectionPool
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connection pooling."""

    _pool: Optional[ConnectionPool] = None

    @classmethod
    def initialize_pool(cls, database_url: Optional[str] = None) -> Optional[ConnectionPool]:
        """Initialize connection pool if database_url is provided."""
        if cls._pool is not None and not cls._pool.closed:
            return cls._pool

        db_url = database_url or get_settings().database_url
        if not db_url:
            logger.warning("DATABASE_URL is not set. Database operations requiring PostgreSQL will fail.")
            return None

        try:
            # Psycopg 3 connection pool configured for Supabase Transaction Pooler (disables prepared statements)
            cls._pool = ConnectionPool(
                conninfo=db_url,
                min_size=1,
                max_size=10,
                open=True,
                timeout=10.0,
                kwargs={"prepare_threshold": None},
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
            return cls._pool
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL connection pool: %s", e)
            cls._pool = None
            raise

    @classmethod
    def close_pool(cls) -> None:
        """Close connection pool cleanly."""
        if cls._pool is not None and not cls._pool.closed:
            try:
                cls._pool.close()
                logger.info("PostgreSQL connection pool closed.")
            except Exception as e:
                logger.error("Error closing database connection pool: %s", e)
            finally:
                cls._pool = None

    @classmethod
    def get_pool(cls) -> Optional[ConnectionPool]:
        """Get the active pool instance."""
        return cls._pool

    @classmethod
    def check_health(cls) -> bool:
        """Check if database connection is alive."""
        if cls._pool is None or cls._pool.closed:
            return False
        try:
            with cls._pool.connection(timeout=3.0) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    result = cur.fetchone()
                    return result is not None and result[0] == 1
        except Exception as e:
            logger.warning("Database health check probe failed: %s", e)
            return False


def get_db_pool() -> Optional[ConnectionPool]:
    """Dependency provider for database pool."""
    return DatabaseManager.get_pool()
