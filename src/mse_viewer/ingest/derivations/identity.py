"""Stored-identity computation: ``Basic X`` prefix and collision-suffix logic."""
from __future__ import annotations

from typing import Iterable


def compute_identity(
    *,
    display_name: str,
    super_type: str,
    existing_identities: Iterable[str] = (),
) -> str:
    """Compute the stored ``name`` (= identity) for a card.

    Rules (init_prompt_2 §3):
      - If ``super_type`` starts with ``Basic`` then identity = ``"Basic <display_name>"``.
        Multiple Basic-X cards collapse onto the same identity (one record holds
        all alt-art labels).
      - Otherwise identity = ``display_name``.
      - If that identity already exists in ``existing_identities`` we are in a
        conflict — the *caller* is expected to surface a review modal.  This
        function returns the bare identity; collision-suffix candidates such
        as ``"<name> 2"`` are produced by :func:`next_collision_suffix`.
    """
    name = display_name.strip()
    if super_type.strip().lower().startswith("basic"):
        return f"Basic {name}"
    return name


def next_collision_suffix(base: str, existing_identities: Iterable[str]) -> str:
    """Return the next free ``"<base> N"`` suffix not present in ``existing_identities``."""
    existing = set(existing_identities)
    if base not in existing:
        return base
    n = 2
    while f"{base} {n}" in existing:
        n += 1
    return f"{base} {n}"
