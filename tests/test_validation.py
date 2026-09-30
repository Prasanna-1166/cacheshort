"""Unit tests for URL request validation."""

import pytest
from pydantic import ValidationError
from app.schemas.url import URLCreateRequest


def test_valid_http_and_https_urls():
    """Verify standard HTTP and HTTPS URLs are accepted."""
    valid_urls = [
        "http://example.com",
        "https://example.com",
        "https://sub.domain.org/path/to/resource?query=1&b=2#section",
        "https://example.com:8080/test",
    ]
    for url in valid_urls:
        req = URLCreateRequest(url=url)
        assert req.url == url


def test_reject_empty_or_whitespace_urls():
    """Verify empty or whitespace-only inputs are rejected."""
    invalid_urls = ["", "   ", "\t\n"]
    for url in invalid_urls:
        with pytest.raises(ValidationError):
            URLCreateRequest(url=url)


def test_reject_unsupported_schemes():
    """Verify non-HTTP/HTTPS schemes are rejected."""
    invalid_urls = [
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "mailto:test@example.com",
        "example.com",  # Missing scheme
    ]
    for url in invalid_urls:
        with pytest.raises(ValidationError):
            URLCreateRequest(url=url)


def test_reject_missing_host():
    """Verify URLs without host are rejected."""
    with pytest.raises(ValidationError):
        URLCreateRequest(url="http://")


def test_reject_excessive_url_length():
    """Verify URLs exceeding 2048 characters are rejected."""
    long_url = "https://example.com/" + ("a" * 2050)
    with pytest.raises(ValidationError):
        URLCreateRequest(url=long_url)
