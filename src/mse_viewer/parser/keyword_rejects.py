"""Explicit reject-list for keyword identities.

Phase 1.6 prompt 3 change 13: certain match-strings are never legitimate
keywords (e.g. ``Evolve <atom-param>n</atom-param>`` — the user only authors
``Evolve <atom-param>name</atom-param>``). When we see one in a file or as a
card-side reference, drop it and log so the user can audit later.

The match logic is structural — we compare against canonicalized match
strings AND against bare card-side references (e.g. ``Evolve 4``) so the
filter catches both source paths.
"""
from __future__ import annotations

import re


# A bare card-side reference matching one of these patterns is rejected.
# Each entry is a regex applied case-insensitively to the *cleaned* ref
# (after stripping tags / outer whitespace).
_REJECTED_REF_PATTERNS: tuple[re.Pattern[str], ...] = (
    # ``Evolve 1`` / ``Evolve 23`` — the digits-form. The legitimate keyword
    # is ``Evolve <name>`` (creature reference), never a number.
    re.compile(r"^evolve\s+\d+$", re.IGNORECASE),
)

# A keyword:match identity matching one of these is rejected at parse time.
_REJECTED_MATCH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^evolve\s+<atom-param>\s*(?:n|number|cost|count)\s*</atom-param>$",
        re.IGNORECASE,
    ),
    re.compile(r"^evolve\s+\d+$", re.IGNORECASE),
)


def is_rejected_match(match_string: str) -> bool:
    """Return True for keyword definitions we never want stored."""
    s = (match_string or "").strip()
    if not s:
        return False
    return any(p.match(s) for p in _REJECTED_MATCH_PATTERNS)


def is_rejected_ref(ref_text: str) -> bool:
    """Return True for card-side references we never want resolved."""
    s = (ref_text or "").strip()
    if not s:
        return False
    return any(p.match(s) for p in _REJECTED_REF_PATTERNS)
