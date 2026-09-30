"""API Key lifecycle management endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.rate_limiter import rate_limit_dependency
from app.core.security import generate_api_key, verify_api_key
from app.database.api_key_repository import (
    BaseAPIKeyRepository,
    get_api_key_repository,
)
from app.schemas.api_key import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyInfoResponse,
    APIKeyRevokeResponse,
)

router = APIRouter(prefix="/api/keys", tags=["API Key Management"])


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="Create API Key",
    description="Generate a new cryptographically secure API key. The unhashed raw key is returned exactly once and cannot be recovered later.",
)
def create_key(
    payload: APIKeyCreateRequest,
    repo: BaseAPIKeyRepository = Depends(get_api_key_repository),
) -> APIKeyCreateResponse:
    """Create and persist a new hashed API key record."""
    raw_key, key_prefix, key_hash = generate_api_key()

    try:
        record = repo.create_api_key(
            name=payload.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate and store API key.",
        )

    return APIKeyCreateResponse(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        raw_key=raw_key,
        created_at=record.created_at,
    )


@router.get(
    "",
    response_model=List[APIKeyInfoResponse],
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="List API Keys",
    description="List metadata for all active and revoked API keys. Hashes and raw keys are never exposed.",
)
def list_keys(
    repo: BaseAPIKeyRepository = Depends(get_api_key_repository),
) -> List[APIKeyInfoResponse]:
    """Retrieve metadata for all stored API keys."""
    records = repo.list_all_keys()
    return [
        APIKeyInfoResponse(
            id=r.id,
            name=r.name,
            key_prefix=r.key_prefix,
            is_active=r.is_active,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in records
    ]


@router.delete(
    "/{key_id}",
    response_model=APIKeyRevokeResponse,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="Revoke API Key",
    description="Deactivate an API key immediately. Revoked keys cannot be used for authentication.",
)
def revoke_key(
    key_id: int,
    repo: BaseAPIKeyRepository = Depends(get_api_key_repository),
) -> APIKeyRevokeResponse:
    """Deactivate an existing API key by ID."""
    record = repo.get_by_id(key_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    if not record.is_active or record.revoked_at is not None:
        return APIKeyRevokeResponse(
            id=key_id,
            revoked=False,
            message="API key is already revoked or inactive",
        )

    success = repo.revoke_key(key_id)
    return APIKeyRevokeResponse(
        id=key_id,
        revoked=success,
        message="API key successfully revoked",
    )
