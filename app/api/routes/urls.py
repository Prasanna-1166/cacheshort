"""URL shortening, redirection, and analytics endpoints."""

import re
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.url import (
    URLCreateRequest,
    URLCreateResponse,
    URLInfoResponse,
    URLStatsResponse,
)
from app.services.url_service import URLService, get_url_service, ShortCodeGenerationError

router = APIRouter(tags=["URLs"])

# Valid short code pattern: alphanumeric characters, underscores, hyphens between 1 and 16 chars
SHORT_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,16}$")


@router.post(
    "/api/urls",
    response_model=URLCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="Create Short URL",
    description="Generate a new short code for a given target URL, persist it, and add to LRU cache.",
)
def create_short_url(
    payload: URLCreateRequest,
    url_service: URLService = Depends(get_url_service),
) -> URLCreateResponse:
    try:
        result = url_service.create_short_url(original_url=payload.url)
        return URLCreateResponse(**result)
    except ShortCodeGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to generate unique short code: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the short URL.",
        )


@router.get(
    "/api/urls/{short_code}/stats",
    response_model=URLStatsResponse,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="Get Short URL Analytics",
    description="Fetch access statistics and creation timestamps for a given short code.",
)
def get_short_url_stats(
    short_code: str,
    url_service: URLService = Depends(get_url_service),
) -> URLStatsResponse:
    if not SHORT_CODE_PATTERN.match(short_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid short code format",
        )

    record = url_service.get_url_details(short_code)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found",
        )

    return URLStatsResponse(
        short_code=record.short_code,
        original_url=record.original_url,
        created_at=record.created_at,
        last_accessed_at=record.last_accessed_at,
        access_count=record.access_count,
    )


@router.get(
    "/api/urls/{short_code}",
    response_model=URLInfoResponse,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_dependency)],
    summary="Get Short URL Details",
    description="Fetch metadata for a given short code.",
)
def get_short_url_info(
    short_code: str,
    url_service: URLService = Depends(get_url_service),
) -> URLInfoResponse:
    if not SHORT_CODE_PATTERN.match(short_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid short code format",
        )

    record = url_service.get_url_details(short_code)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found",
        )

    return URLInfoResponse(
        id=record.id,
        short_code=record.short_code,
        original_url=record.original_url,
        created_at=record.created_at,
        last_accessed_at=record.last_accessed_at,
        access_count=record.access_count,
    )


@router.get(
    "/{short_code}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    dependencies=[Depends(rate_limit_dependency)],
    summary="Redirect to Original URL",
    description="Resolves short code using custom LRU cache first, falling back to PostgreSQL on cache miss.",
    responses={
        307: {"description": "Redirecting to original destination URL"},
        400: {"description": "Invalid short code format"},
        404: {"description": "Short code not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
def redirect_to_url(
    short_code: str,
    background_tasks: BackgroundTasks,
    url_service: URLService = Depends(get_url_service),
) -> RedirectResponse:
    if not SHORT_CODE_PATTERN.match(short_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid short code format",
        )

    original_url = url_service.resolve_short_code(short_code)
    if not original_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short code not found",
        )

    # Record persistent analytics in background without blocking fast cache-hit redirect
    background_tasks.add_task(url_service.record_access, short_code)

    return RedirectResponse(
        url=original_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
