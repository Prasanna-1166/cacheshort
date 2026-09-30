"""Unit tests for the custom LRU Cache implementation."""

import pytest
from app.cache.lru_cache import LRUCache


def test_empty_cache():
    """Verify state of a newly created cache."""
    cache = LRUCache(capacity=3)
    assert cache.size() == 0
    assert len(cache) == 0
    assert cache.get("nonexistent") is None
    assert cache.keys_in_order() == []


def test_put_and_get():
    """Verify basic put and get operations."""
    cache = LRUCache(capacity=3)
    cache.put("k1", "v1")
    cache.put("k2", "v2")

    assert cache.size() == 2
    assert cache.get("k1") == "v1"
    assert cache.get("k2") == "v2"


def test_missing_key():
    """Verify lookup of missing keys returns None without error."""
    cache = LRUCache(capacity=2)
    cache.put("a", 1)
    assert cache.get("b") is None
    assert "b" not in cache


def test_update_existing_key():
    """Verify updating a key modifies value and updates recency."""
    cache = LRUCache(capacity=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.keys_in_order() == ["b", "a"]

    # Updating 'a' should make 'a' MRU and change value
    cache.put("a", 100)
    assert cache.get("a") == 100
    assert cache.size() == 2
    assert cache.keys_in_order() == ["a", "b"]

    # Adding 'c' should now evict 'b' (the actual LRU)
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 100
    assert cache.get("c") == 3
    assert cache.keys_in_order() == ["c", "a"]


def test_capacity_limit_and_eviction():
    """Verify simple eviction when capacity limit is reached."""
    cache = LRUCache(capacity=2)
    cache.put("A", 1)
    cache.put("B", 2)
    cache.put("C", 3)

    # 'A' should be evicted because it was least recently used
    assert cache.get("A") is None
    assert cache.get("B") == 2
    assert cache.get("C") == 3
    assert cache.size() == 2
    assert cache.keys_in_order() == ["C", "B"]


def test_access_changes_recency_conceptual_sequence():
    """Verify standard sequence: put A, put B, get A, put C -> B evicted."""
    cache = LRUCache(capacity=2)
    cache.put("A", "val_a")
    cache.put("B", "val_b")

    # Access A -> A becomes MRU, B becomes LRU
    val_a = cache.get("A")
    assert val_a == "val_a"
    assert cache.keys_in_order() == ["A", "B"]

    # Put C -> B should be evicted, A and C remain
    cache.put("C", "val_c")
    assert cache.get("A") == "val_a"
    assert cache.get("B") is None
    assert cache.get("C") == "val_c"
    assert cache.keys_in_order() == ["C", "A"]


def test_multiple_evictions():
    """Verify consecutive evictions across capacity changes."""
    cache = LRUCache(capacity=3)
    cache.put("1", "one")
    cache.put("2", "two")
    cache.put("3", "three")
    assert cache.keys_in_order() == ["3", "2", "1"]

    cache.put("4", "four")
    # '1' evicted
    assert cache.keys_in_order() == ["4", "3", "2"]
    assert cache.get("1") is None

    cache.put("5", "five")
    # '2' evicted
    assert cache.keys_in_order() == ["5", "4", "3"]
    assert cache.get("2") is None


def test_remove():
    """Verify removing keys directly."""
    cache = LRUCache(capacity=3)
    cache.put("x", 10)
    cache.put("y", 20)
    cache.put("z", 30)

    # Remove existing
    removed = cache.remove("y")
    assert removed is True
    assert cache.get("y") is None
    assert cache.size() == 2
    assert cache.keys_in_order() == ["z", "x"]

    # Remove non-existing
    removed_again = cache.remove("y")
    assert removed_again is False

    # Remove head
    assert cache.remove("z") is True
    assert cache.keys_in_order() == ["x"]

    # Remove remaining
    assert cache.remove("x") is True
    assert cache.size() == 0
    assert cache.keys_in_order() == []


def test_clear():
    """Verify clearing entire cache resets pointers and size."""
    cache = LRUCache(capacity=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.size() == 2

    cache.clear()
    assert cache.size() == 0
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.keys_in_order() == []

    # Can put new items after clear
    cache.put("c", 3)
    assert cache.get("c") == 3
    assert cache.size() == 1


def test_capacity_one():
    """Verify edge case with capacity = 1."""
    cache = LRUCache(capacity=1)
    cache.put("first", 1)
    assert cache.get("first") == 1
    assert cache.size() == 1

    cache.put("second", 2)
    assert cache.get("first") is None
    assert cache.get("second") == 2
    assert cache.size() == 1
    assert cache.keys_in_order() == ["second"]


def test_invalid_capacity():
    """Verify ValueError is raised on non-positive capacity."""
    with pytest.raises(ValueError, match="Cache capacity must be a positive integer"):
        LRUCache(capacity=0)

    with pytest.raises(ValueError, match="Cache capacity must be a positive integer"):
        LRUCache(capacity=-5)


def test_repeated_access_ordering():
    """Verify repeated gets correctly shift MRU position repeatedly."""
    cache = LRUCache(capacity=4)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    cache.put("d", 4)
    # Order: [d, c, b, a]
    assert cache.keys_in_order() == ["d", "c", "b", "a"]

    # Access 'b' -> [b, d, c, a]
    cache.get("b")
    assert cache.keys_in_order() == ["b", "d", "c", "a"]

    # Access 'a' -> [a, b, d, c]
    cache.get("a")
    assert cache.keys_in_order() == ["a", "b", "d", "c"]

    # Put 'e' -> 'c' evicted -> [e, a, b, d]
    cache.put("e", 5)
    assert cache.keys_in_order() == ["e", "a", "b", "d"]
    assert cache.get("c") is None
