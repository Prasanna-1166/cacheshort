"""Unit tests for LRUCache observability metrics."""

import threading
from app.cache.lru_cache import LRUCache


def test_cache_metrics_initial_state():
    """Verify metrics start at zero for a fresh cache."""
    cache = LRUCache(capacity=3)
    stats = cache.stats()

    assert stats["capacity"] == 3
    assert stats["current_size"] == 0
    assert stats["total_gets"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["evictions"] == 0
    assert stats["hit_rate"] == 0.0


def test_cache_hit_and_miss_tracking():
    """Verify hits and misses are tracked accurately."""
    cache = LRUCache(capacity=3)
    cache.put("k1", "v1")
    cache.put("k2", "v2")

    # Miss
    assert cache.get("missing") is None
    # Hit
    assert cache.get("k1") == "v1"
    # Hit
    assert cache.get("k2") == "v2"
    # Miss
    assert cache.get("missing2") is None

    stats = cache.stats()
    assert stats["total_gets"] == 4
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["hit_rate"] == 0.5


def test_cache_eviction_counter():
    """Verify eviction counter increments only when items are discarded due to capacity."""
    cache = LRUCache(capacity=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.stats()["evictions"] == 0

    # Overwrite existing key: no eviction
    cache.put("a", 100)
    assert cache.stats()["evictions"] == 0

    # Insert 3rd key: 'b' is evicted
    cache.put("c", 3)
    assert cache.stats()["evictions"] == 1

    # Insert 4th key: 'a' is evicted
    cache.put("d", 4)
    assert cache.stats()["evictions"] == 2


def test_cache_metrics_reset():
    """Verify reset_metrics zeroes out counters while preserving cache contents."""
    cache = LRUCache(capacity=3)
    cache.put("a", 1)
    cache.get("a")
    cache.get("missing")

    stats = cache.stats()
    assert stats["total_gets"] == 2
    assert stats["hits"] == 1
    assert stats["misses"] == 1

    cache.reset_metrics()
    new_stats = cache.stats()
    assert new_stats["total_gets"] == 0
    assert new_stats["hits"] == 0
    assert new_stats["misses"] == 0
    assert new_stats["current_size"] == 1
    assert cache.get("a") == 1


def test_cache_metrics_thread_safety():
    """Verify metrics consistency under multithreaded concurrent access."""
    cache = LRUCache(capacity=50)
    for i in range(25):
        cache.put(f"key_{i}", i)

    def worker():
        for i in range(100):
            # Alternate between hit and miss
            if i % 2 == 0:
                cache.get(f"key_{i % 25}")
            else:
                cache.get(f"missing_{i}")

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = cache.stats()
    assert stats["total_gets"] == 1000
    assert stats["hits"] == 500
    assert stats["misses"] == 500
    assert stats["hit_rate"] == 0.5
