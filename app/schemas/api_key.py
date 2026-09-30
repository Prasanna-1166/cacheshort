"""Pydantic schemas for API Key metadata and authentication models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class APIKeyInfoResponse(BaseModel):
    """Safe public metadata for an API key (never exposes raw key or hash)."""

    id: int = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Human-readable name or label for the API key")
    key_prefix: str = Field(..., description="Non-sensitive key prefix for identification (e.g., cs_live_...)")
    is_active: bool = Field(..., description="Whether this key is currently active")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Timestamp when the key was last used")
    revoked_at: Optional[datetime] = Field(None, description="Timestamp when the key was revoked, if applicable")


class APIKeyCreateResponse(BaseModel):
    """Response returned upon key generation containing raw key displayed only once."""

    id: int = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Human-readable name or label for the API key")
    key_prefix: str = Field(..., description="Key prefix")
    raw_key: str = Field(..., description="The unhashed API key (displayed only once upon creation)")
    created_at: datetime = Field(..., description="Creation timestamp")
