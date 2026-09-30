"""Doubly Linked List Node for LRU Cache."""

from typing import Any, Optional


class Node:
    """A Node in a Doubly Linked List storing key-value pairs."""

    __slots__ = ("key", "value", "prev", "next")

    def __init__(
        self,
        key: Any = None,
        value: Any = None,
        prev: Optional["Node"] = None,
        next_node: Optional["Node"] = None,
    ):
        self.key: Any = key
        self.value: Any = value
        self.prev: Optional["Node"] = prev
        self.next: Optional["Node"] = next_node

    def __repr__(self) -> str:
        return f"Node(key={self.key!r}, value={self.value!r})"
