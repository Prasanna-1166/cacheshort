"""Unit tests for sliding window rate limiter."""

import time
from app.core.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_allows_under_limit():
    """Verify requests under the limit are permitted."""
    limiter = SlidingWindowRateLimiter(requests=3, window_seconds=10)
    client_id = "client_1"

    allowed1, retry_after1 = limiter.is_allowed(client_id)
    assert allowed1 is True
    assert retry_after1 == 0

    allowed2, retry_after2 = limiter.is_allowed(client_id)
    assert allowed2 is True
    assert retry_after2 == 0


def test_rate_limiter_blocks_over_limit_with_retry_after():
    """Verify exceeding the limit blocks requests and returns positive Retry-After."""
    limiter = SlidingWindowRateLimiter(requests=2, window_seconds=5)
    client = "client_test"

    # 1st request -> OK
    assert limiter.is_allowed(client)[0] is True
    # 2nd request -> OK
    assert limiter.is_allowed(client)[0] is True
    # 3rd request -> BLOCKED
    allowed, retry_after = limiter.is_allowed(client)
    assert allowed is False
    assert 1 <= retry_after <= 5


def test_rate_limiter_resets_after_window():
    """Verify requests are allowed again after the window expires."""
    limiter = SlidingWindowRateLimiter(requests=1, window_seconds=1)
    client = "client_reset"

    # 1st request -> OK
    assert limiter.is_allowed(client)[0] is True
    # 2nd immediate request -> BLOCKED
    assert limiter.is_allowed(client)[0] is False

    # Sleep past window
    time.sleep(1.1)

    # 3rd request -> OK
    allowed, retry_after = limiter.is_allowed(client)
    assert allowed is True
    assert retry_after == 0


def test_rate_limiter_isolated_per_client():
    """Verify different clients have independent rate limit tracking."""
    limiter = SlidingWindowRateLimiter(requests=1, window_seconds=10)

    # Client A exceeds limit
    assert limiter.is_allowed("client_A")[0] is True
    assert limiter.is_allowed("client_A")[0] is False

    # Client B should still be allowed
    assert limiter.is_allowed("client_B")[0] is True


def test_rate_limiter_disabled():
    """Verify rate limiter permits all requests when disabled."""
    limiter = SlidingWindowRateLimiter(requests=1, window_seconds=10, enabled=False)
    client = "client_disabled"

    for _ in range(5):
        allowed, retry_after = limiter.is_allowed(client)
        assert allowed is True
        assert retry_after == 0


def test_rate_limiter_prune_expired():
    """Verify pruning removes stale client entries."""
    limiter = SlidingWindowRateLimiter(requests=2, window_seconds=1, cleanup_interval_seconds=0.0)
    limiter.is_allowed("stale_client")

    assert "stale_client" in limiter._records
    time.sleep(1.1)

    # Calling is_allowed triggers periodic prune
    limiter.is_allowed("new_client")
    assert "stale_client" not in limiter._records
    assert "new_client" in limiter._records
