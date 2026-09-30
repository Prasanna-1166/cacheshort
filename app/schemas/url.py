"""Pydantic schemas for URL operations and Health."""

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator


MAX_URL_LENGTH = 2048


class URLCreateRequest(BaseModel):
    """Payload for creating a short URL."""

    url: str = Field(
        ...,
        description="The original target URL to be shortened",
        examples=["https://example.com/very/long/path?param=value"],
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("URL cannot be empty")

        v = v.strip()
        if not v:
            raise ValueError("URL cannot be empty or only whitespace")

        if len(v) > MAX_URL_LENGTH:
            raise ValueError(f"URL length exceeds maximum allowed limit of {MAX_URL_LENGTH} characters")

        try:
            parsed = urlparse(v)
        except Exception as e:
            raise ValueError(f"Malformed URL: {e}")

        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError("URL scheme must be either 'http' or 'https'")

        if not parsed.netloc:
            raise ValueError("URL must include a valid host/domain name")

        return v


class URLCreateResponse(BaseModel):
    """Response returned when a short URL is created."""

    short_code: str = Field(..., description="The unique short code")
    short_url: str = Field(..., description="The full resolvable short URL")
    original_url: str = Field(..., description="The original target URL")


class URLInfoResponse(BaseModel):
    """Detailed URL metadata schema."""

    id: int
    short_code: str
    original_url: str
    created_at: datetime
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0


class URLStatsResponse(BaseModel):
    """URL Analytics statistics response schema."""

    short_code: str = Field(..., description="The unique short code identifier")
    original_url: str = Field(..., description="The destination target URL")
    created_at: datetime = Field(..., description="Timestamp when the short URL was created")
    last_accessed_at: Optional[datetime] = Field(None, description="Timestamp of the most recent database-backed resolution")
    access_count: int = Field(..., description="Total database-backed resolution count")


class HealthResponse(BaseModel):
    """Application health status response."""

    status: str = Field(..., description="Overall service health status")
    environment: str = Field(..., description="Current application environment")
    cache_size: int = Field(..., description="Number of entries currently stored in LRU cache")
    cache_capacity: int = Field(..., description="Maximum configured capacity of LRU cache")
    database: str = Field(..., description="Database connection status")
    uptime_seconds: float = Field(..., description="Process uptime in seconds since initialization")

