from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class APIKeyCreateRequest(BaseModel):
    """Payload for creating a new named API key."""

    name: str = Field(
        ...,
        description="Human-readable label for the API key",
        examples=["production-service", "ci-cd-pipeline"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Key name cannot be empty")
        v = v.strip()
        if not v:
            raise ValueError("Key name cannot be empty or only whitespace")
        if len(v) > 64:
            raise ValueError("Key name cannot exceed 64 characters")
        return v


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


class APIKeyRevokeResponse(BaseModel):
    """Response returned upon revoking an API key."""

    id: int = Field(..., description="Unique key identifier")
    revoked: bool = Field(..., description="Whether the key was successfully revoked")
    message: str = Field(..., description="Status message regarding the revocation operation")

