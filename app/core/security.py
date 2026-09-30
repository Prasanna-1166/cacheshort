"""Cryptographic security utilities and FastAPI authentication dependencies."""

import hashlib
import secrets
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.database.api_key_repository import (
    APIKeyRecord,
    BaseAPIKeyRepository,
    get_api_key_repository,
)

API_KEY_PREFIX = "cs_live_"
API_KEY_HEADER_NAME = "X-API-Key"

api_key_header_scheme = APIKeyHeader(
    name=API_KEY_HEADER_NAME,
    auto_error=False,
    description="Database-backed API key authentication header.",
)


def generate_api_key() -> Tuple[str, str, str]:
    """Generate a cryptographically secure random API key.

    Returns:
        Tuple of (raw_key, key_prefix, key_hash):
        - raw_key: The plaintext key with 'cs_live_' prefix (to be shown only once)
        - key_prefix: Non-sensitive 12-char prefix for display identification
        - key_hash: SHA-256 hex digest of the raw key to be stored in PostgreSQL
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{API_KEY_PREFIX}{random_part}"
    key_prefix = raw_key[:12]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


def hash_api_key(raw_key: str) -> str:
    """Compute SHA-256 hexadecimal digest of raw API key."""
    if not isinstance(raw_key, str):
        raise ValueError("API key must be a string")
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def validate_api_key_format(raw_key: Optional[str]) -> bool:
    """Check if the provided API key matches the required format without verifying against DB."""
    if not raw_key or not isinstance(raw_key, str):
        return False
    clean_key = raw_key.strip()
    return clean_key.startswith(API_KEY_PREFIX) and len(clean_key) >= 16


def verify_api_key(
    raw_api_key: Optional[str] = Security(api_key_header_scheme),
    api_key_repo: BaseAPIKeyRepository = Depends(get_api_key_repository),
) -> APIKeyRecord:
    """FastAPI authentication dependency enforcing database-backed API key verification.

    Raises:
        HTTPException (401 Unauthorized) if the key is missing, malformed, inactive,
        revoked, or does not exist in the database. Never leaks the specific reason
        for failure.
    """
    unauthorized_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": f"ApiKey name=\"{API_KEY_HEADER_NAME}\""},
    )

    if not raw_api_key or not validate_api_key_format(raw_api_key):
        raise unauthorized_exception

    provided_hash = hash_api_key(raw_api_key)
    record = api_key_repo.get_by_hash(provided_hash)

    if not record or not record.is_active or record.revoked_at is not None:
        raise unauthorized_exception

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(provided_hash, record.key_hash):
        raise unauthorized_exception

    # Record last used timestamp
    api_key_repo.update_last_used(record.id)

    return record
