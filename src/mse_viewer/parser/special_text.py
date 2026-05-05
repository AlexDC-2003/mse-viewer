"""Shared text helpers for special frames (Saga, Leyline, Planeswalker).

Italic-flavor extraction operates on RAW (pre-canonicalize) text so that
keyword-reminder italics — which live inside ``<atom-reminder...>`` blocks —
can be told apart from genuine flavor italics that just happen to be inline.

After canonicalization, both shapes look like ``<i>...</i>``; doing the split
upstream is what makes it reliable.
"""
from __future__ import annotations

import re

# An <atom-reminder...>...</atom-reminder...> block. Anything between its tags
# is keyword reminder text, NOT flavor — masked before italic extraction.
_RE_ATOM_REMINDER_SPAN = re.compile(
    r"<atom-reminder(?:-[^>\s]+)?(?:\s[^>]*)?>.*?</atom-reminder(?:-[^>\s]+)?(?:\s[^>]*)?>",
    re.DOTALL | re.IGNORECASE,
)

# A bare italic span (any of MSE's italic variants). Captured group 2 is the
# inner text.
_RE_ITALIC_SPAN = re.compile(
    r"<(i|i-auto|i-flavor)>(.*?)</\1>",
    re.DOTALL | re.IGNORECASE,
)

# Continuation-line whitespace MSE writes into multi-line values (tabs).
_RE_LINE_LEADING_WS = re.compile(r"^[ \t]+", re.MULTILINE)


def extract_italic_flavor(
    raw: str,
    *,
    protect_first_line: bool = False,
) -> tuple[str, str]:
    """Split italic-only flavor out of a raw rule_text / special_text body.

    Operates on the RAW text (before :func:`canonicalize_text`). Italic spans
    that sit *inside* an ``<atom-reminder...>`` wrapper are preserved on the
    rule_text side (those are keyword reminders); other italic spans are pulled
    into the flavor return value.

    ``protect_first_line``: when ``True``, the first non-empty line is held
    back from the splitter and copied verbatim into the rule_text return.
    Used by Saga where the first segment is a Read-ahead reminder or the
    ``(As this Saga enters... Sacrifice after X.)`` template that, by user
    rule, is never flavor.

    Returns ``(rule_text_raw, flavor_text_raw)``. Both halves still need
    :func:`canonicalize_text` / :func:`canonicalize_flavor` from the caller.
    """
    if not raw:
        return raw or "", ""

    if protect_first_line:
        head, _, tail = raw.partition("\n")
        # Skip blank leading lines so the "first line" is the first with content.
        while head.strip() == "" and tail:
            head_next, _, tail = tail.partition("\n")
            head = (head + "\n" + head_next) if head else head_next
        cleaned_tail, flavor = _split(tail)
        rule = head if not cleaned_tail else f"{head}\n{cleaned_tail}"
        return rule, flavor

    return _split(raw)


def _split(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    # Mask atom-reminder spans so their inner italics aren't pulled out.
    placeholders: dict[str, str] = {}

    def _mask(m: re.Match[str]) -> str:
        token = f"\x00ATOMR{len(placeholders)}\x00"
        placeholders[token] = m.group(0)
        return token

    masked = _RE_ATOM_REMINDER_SPAN.sub(_mask, text)

    flavor_parts: list[str] = []

    def _consume(m: re.Match[str]) -> str:
        flavor_parts.append(m.group(2).strip())
        return ""

    cleaned = _RE_ITALIC_SPAN.sub(_consume, masked)

    # Restore atom-reminder spans verbatim.
    for token, original in placeholders.items():
        cleaned = cleaned.replace(token, original)

    # Tidy any trailing whitespace runs and collapse fully-blank lines that
    # the strip left behind.
    cleaned_lines = [ln.rstrip() for ln in cleaned.splitlines()]
    cleaned_lines = [ln for ln in cleaned_lines if ln.strip() or False]
    rule_text_raw = "\n".join(cleaned_lines)

    flavor_raw = "\n".join(p for p in flavor_parts if p)
    return rule_text_raw, flavor_raw


def parse_starting_loyalty(raw: str | None) -> int | None:
    """Coerce MSE ``loyalty:`` to ``int | None``.

    Empty / non-integer values (``""``, ``X``, ``"4*"``, etc.) collapse to
    ``None``. Per the user direction in Phase 1.6: only integer values land
    in the column.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None
