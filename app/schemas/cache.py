"""Pydantic schema for Cache observability metrics."""

from pydantic import BaseModel, Field


class CacheStatsResponse(BaseModel):
    """Observability response schema for the in-memory LRU cache."""

    capacity: int = Field(..., description="Maximum configured capacity of the LRU cache")
    current_size: int = Field(..., description="Number of entries currently stored in the LRU cache")
    total_gets: int = Field(..., description="Total number of cache lookup requests received")
    hits: int = Field(..., description="Number of successful cache hits")
    misses: int = Field(..., description="Number of cache misses")
    evictions: int = Field(..., description="Number of least-recently-used entries evicted")
    hit_rate: float = Field(..., description="Proportion of cache lookups that were hits (0.0 to 1.0)")


class CacheEvictionResponse(BaseModel):
    """Response returned upon administrative cache key eviction."""

    short_code: str = Field(..., description="The short code targeted for eviction")
    evicted: bool = Field(..., description="Whether the entry was found in memory and evicted")
    message: str = Field(..., description="Status description of the eviction action")


class CacheClearResponse(BaseModel):
    """Response returned upon administrative cache flush."""

    cleared_entries: int = Field(..., description="Count of cache items evicted during clear operation")
    message: str = Field(..., description="Status description of the clear action")

