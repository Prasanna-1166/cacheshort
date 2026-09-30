"""URL Service managing short-code generation, database access, and LRU cache."""

import logging
import secrets
import string
from typing import Optional
from fastapi import Depends

from app.cache.lru_cache import LRUCache
from app.core.config import Settings, get_settings
from app.database.repository import (
    BaseURLRepository,
    DuplicateShortCodeError,
    URLRecord,
    get_repository,
)

logger = logging.getLogger(__name__)

# Base62 character set (alphanumeric, URL-safe)
BASE62_ALPHABET = string.ascii_letters + string.digits
DEFAULT_CODE_LENGTH = 7
MAX_COLLISION_RETRIES = 5


class ShortCodeGenerationError(Exception):
    """Raised when unique short code generation exceeds maximum retry limit."""
    pass


class URLService:
    """Application service for shortening and resolving URLs with LRU Cache."""

    def __init__(
        self,
        repository: BaseURLRepository,
        cache: LRUCache,
        base_url: str = "http://localhost:8000",
    ):
        self.repository = repository
        self.cache = cache
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def generate_random_code(length: int = DEFAULT_CODE_LENGTH) -> str:
        """Generate a random URL-safe Base62 short code string."""
        return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))

    def create_short_url(self, original_url: str) -> dict:
        """Create a new short code for the provided original URL.

        Attempts direct insertion into the database to rely on the database's
        UNIQUE constraint as the authoritative uniqueness guarantee.
        Catches duplicate violations and retries with bounded attempts.
        """
        for attempt in range(MAX_COLLISION_RETRIES):
            candidate = self.generate_random_code()
            try:
                # Attempt direct insertion — UNIQUE constraint is the authoritative check
                record = self.repository.create_url(short_code=candidate, original_url=original_url)

                # Update custom in-memory LRU cache
                self.cache.put(candidate, record.original_url)

                short_url = f"{self.base_url}/{candidate}"
                return {
                    "short_code": candidate,
                    "short_url": short_url,
                    "original_url": record.original_url,
                }
            except DuplicateShortCodeError:
                logger.warning(
                    "Short code collision detected on candidate '%s' (attempt %d/%d). Retrying...",
                    candidate,
                    attempt + 1,
                    MAX_COLLISION_RETRIES,
                )
                continue

        raise ShortCodeGenerationError(
            f"Failed to generate a unique short code after {MAX_COLLISION_RETRIES} collision retry attempts."
        )

    def resolve_short_code(self, short_code: str) -> Optional[str]:
        """Resolve a short code to its original URL using cache-first strategy.

        1. Check custom LRU cache (O(1) memory lookup).
        2. If Cache HIT: Return cached original URL immediately with NO database READ.
        3. If Cache MISS: Query PostgreSQL database repository.
        4. If found in database: Populate LRU cache and return original URL.
        5. If not found in database: Return None.
        """
        # Step 1: LRU Cache Lookup (O(1))
        cached_url = self.cache.get(short_code)
        if cached_url is not None:
            logger.debug("Cache HIT for short_code '%s' — zero database READs", short_code)
            return cached_url

        logger.debug("Cache MISS for short_code '%s' — querying database repository", short_code)

        # Step 2: Database Repository Lookup (Only executed on cache miss)
        record = self.repository.get_by_short_code(short_code)
        if record is None:
            return None

        # Step 3: Populate LRU Cache with result
        self.cache.put(short_code, record.original_url)
        return record.original_url

    def record_access(self, short_code: str) -> None:
        """Atomically record access metadata in persistent storage.

        Executed safely in the background so redirect performance is unaffected.
        """
        try:
            self.repository.increment_access(short_code)
        except Exception as e:
            logger.warning("Failed to record access metadata for short_code '%s': %s", short_code, e)

    def get_url_details(self, short_code: str) -> Optional[URLRecord]:
        """Fetch full database record for short code."""
        return self.repository.get_by_short_code(short_code)


# Singleton LRU Cache instance shared within the service layer
_global_cache: Optional[LRUCache] = None


def get_global_cache(settings: Settings = Depends(get_settings)) -> LRUCache:
    """Retrieve or initialize the global LRU cache instance."""
    global _global_cache
    if _global_cache is None or _global_cache.capacity != settings.cache_capacity:
        _global_cache = LRUCache(capacity=settings.cache_capacity)
    return _global_cache


def get_url_service(
    repository: BaseURLRepository = Depends(get_repository),
    cache: LRUCache = Depends(get_global_cache),
    settings: Settings = Depends(get_settings),
) -> URLService:
    """Dependency injection provider for URLService."""
    return URLService(
        repository=repository,
        cache=cache,
        base_url=settings.base_url,
    )
