from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def append_unique(target: list[T], value: T) -> list[T]:
    """Append-only semantics for JSONB list columns.

    Returns a *new* list so SQLAlchemy notices the JSONB change (mutating in
    place doesn't trigger an UPDATE).  Order is preserved; existing values are
    not duplicated; ``None`` and empty strings are dropped.
    """
    if value is None:
        return list(target)
    if isinstance(value, str) and not value.strip():
        return list(target)
    if value in target:
        return list(target)
    return [*target, value]


def merge_unique(target: list[T], values: Iterable[T]) -> list[T]:
    out = list(target)
    for v in values:
        out = append_unique(out, v)
    return out


def normalize_set_name(name: str) -> str:
    """Set name normalization: trim and store as-typed; comparison is case-insensitive."""
    return name.strip()
