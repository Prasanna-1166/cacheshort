"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: Optional[str] = None
    app_env: str = "development"
    cache_capacity: int = 1000
    base_url: str = "http://localhost:8000"

    # Rate limiting configuration (process-local)
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    rate_limit_enabled: bool = True

    @field_validator("cache_capacity")
    @classmethod
    def validate_cache_capacity(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("cache_capacity must be a positive integer greater than zero")
        return v

    @field_validator("rate_limit_requests")
    @classmethod
    def validate_rate_limit_requests(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("rate_limit_requests must be a positive integer greater than zero")
        return v

    @field_validator("rate_limit_window_seconds")
    @classmethod
    def validate_rate_limit_window_seconds(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("rate_limit_window_seconds must be a positive integer greater than zero")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()
