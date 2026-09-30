"""Custom Least Recently Used (LRU) Cache implementation with observability metrics.

Uses a combination of:
1. Python dict (HashMap) for O(1) key-to-Node lookup.
2. Doubly Linked List with sentinel Head and Tail nodes for O(1) node insertion,
   deletion, and reordering.
3. Thread-safe metrics tracking (hits, misses, evictions, hit rate).

MRU (Most Recently Used) is maintained directly after Sentinel Head.
LRU (Least Recently Used) is maintained directly before Sentinel Tail.
"""

import threading
from typing import Any, Dict, List, Optional
from app.cache.node import Node


class LRUCache:
    """Thread-safe Custom LRU Cache with O(1) operations and metrics tracking."""

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError(f"Cache capacity must be a positive integer (> 0), got: {capacity}")

        self.capacity: int = capacity
        self._map: dict[Any, Node] = {}
        self._lock: threading.RLock = threading.RLock()

        # Observability metrics
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

        # Initialize Sentinel Head and Tail nodes
        self._head: Node = Node()
        self._tail: Node = Node()
        self._head.next = self._tail
        self._tail.prev = self._head

    def _remove_node(self, node: Node) -> None:
        """Unlink node from doubly linked list in O(1)."""
        prev_node = node.prev
        next_node = node.next
        if prev_node:
            prev_node.next = next_node
        if next_node:
            next_node.prev = prev_node

    def _add_to_head(self, node: Node) -> None:
        """Insert node right after sentinel head (MRU position) in O(1)."""
        node.prev = self._head
        node.next = self._head.next
        if self._head.next:
            self._head.next.prev = node
        self._head.next = node

    def _move_to_head(self, node: Node) -> None:
        """Move existing node to MRU position in O(1)."""
        self._remove_node(node)
        self._add_to_head(node)

    def _pop_tail(self) -> Node:
        """Remove and return the least recently used node (before sentinel tail) in O(1)."""
        lru_node = self._tail.prev
        if lru_node and lru_node is not self._head:
            self._remove_node(lru_node)
            return lru_node
        raise RuntimeError("Cannot pop from an empty doubly linked list")

    def get(self, key: Any) -> Optional[Any]:
        """Retrieve value by key in O(1) average time.

        If found, marks the item as Most Recently Used and increments hit counter.
        If not found, increments miss counter and returns None.
        """
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self._misses += 1
                return None

            self._hits += 1
            self._move_to_head(node)
            return node.value

    def put(self, key: Any, value: Any) -> None:
        """Insert or update a key-value pair in O(1) average time.

        If the key exists, updates its value and moves it to MRU position.
        If the key is new, inserts at MRU position.
        If capacity is exceeded, evicts the Least Recently Used item and increments eviction counter.
        """
        with self._lock:
            if key in self._map:
                node = self._map[key]
                node.value = value
                self._move_to_head(node)
                return

            new_node = Node(key=key, value=value)
            self._map[key] = new_node
            self._add_to_head(new_node)

            if len(self._map) > self.capacity:
                # Evict LRU
                lru_node = self._pop_tail()
                if lru_node.key in self._map:
                    del self._map[lru_node.key]
                self._evictions += 1

    def remove(self, key: Any) -> bool:
        """Remove a key from the cache in O(1) average time.

        Returns True if the item was present and removed, False otherwise.
        """
        with self._lock:
            node = self._map.pop(key, None)
            if node is None:
                return False
            self._remove_node(node)
            return True

    def clear(self) -> None:
        """Clear all entries from cache and reset structure in O(1)."""
        with self._lock:
            self._map.clear()
            self._head.next = self._tail
            self._tail.prev = self._head

    def reset_metrics(self) -> None:
        """Reset cache metric counters to zero."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def size(self) -> int:
        """Return current number of elements in cache."""
        with self._lock:
            return len(self._map)

    def stats(self) -> Dict[str, Any]:
        """Return thread-safe snapshot of cache metrics."""
        with self._lock:
            total_gets = self._hits + self._misses
            hit_rate = (self._hits / total_gets) if total_gets > 0 else 0.0
            return {
                "capacity": self.capacity,
                "current_size": len(self._map),
                "total_gets": total_gets,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": round(hit_rate, 4),
            }

    def keys_in_order(self) -> List[Any]:
        """Return cached keys ordered from MRU (head) to LRU (tail).

        Useful for assertions, inspection, and debugging.
        """
        with self._lock:
            result = []
            curr = self._head.next
            while curr and curr is not self._tail:
                result.append(curr.key)
                curr = curr.next
            return result

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._map

    def __len__(self) -> int:
        return self.size()

    def __repr__(self) -> str:
        with self._lock:
            return f"LRUCache(size={len(self._map)}, capacity={self.capacity}, hits={self._hits}, misses={self._misses}, evictions={self._evictions})"
