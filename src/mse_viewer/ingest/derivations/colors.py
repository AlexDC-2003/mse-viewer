"""Color derivation — first-tier-with-content wins (init_prompt_4 #4)."""
from __future__ import annotations

import re

from mse_viewer.parser.models import ParsedCardFace


# Letter → color name. Uppercase comparison; we normalize input.
_COLOR_LETTERS: dict[str, str] = {
    "B": "black",
    "U": "blue",
    "R": "red",
    "G": "green",
    "W": "white",
    "O": "orange",
    "K": "pink",
    "P": "purple",
    "E": "brown",
    "L": "yellow",
    "N": "teal",
}

# Layout hints that should be ignored on the ``card_color`` line.
_LAYOUT_NOISE = {"multicolor", "hybrid", "horizontal", "land", "artifact"}


def _from_casting_cost(cost: str | None) -> list[str]:
    if not cost:
        return []
    found: list[str] = []
    for ch in cost.upper():
        if ch in _COLOR_LETTERS and _COLOR_LETTERS[ch] not in found:
            found.append(_COLOR_LETTERS[ch])
    return found


_RE_COLOR_WORD = re.compile(
    r"\b(black|blue|red|green|white|orange|pink|purple|brown|yellow|teal|colorless)\b",
    re.IGNORECASE,
)


def _from_text_field(value: str | None) -> list[str]:
    if not value:
        return []
    found: list[str] = []
    for m in _RE_COLOR_WORD.finditer(value):
        c = m.group(1).lower()
        if c == "colorless":
            continue
        if c not in found:
            found.append(c)
    return found


def derive_colors(face: ParsedCardFace) -> list[str]:
    """Apply the four-tier rule, returning the *first* tier that yields colors.

    Tiers, in order:
        1. ``casting_cost`` letters (excluding pure colorless).
        2. ``indicator``.
        3. ``extra_data`` (prefer ``extra_indicator`` over ``frame``).
        4. ``card_color``, with layout hints filtered out.
    """
    tier1 = _from_casting_cost(face.casting_cost)
    if tier1:
        return tier1

    tier2 = _from_text_field(face.indicator)
    if tier2:
        return tier2

    extra = face.extra_data or {}
    tier3 = _from_text_field(extra.get("extra_indicator"))
    if tier3:
        return tier3
    tier3 = _from_text_field(extra.get("frame"))
    if tier3:
        return tier3

    cc = face.card_color or ""
    cleaned = ", ".join(p for p in (s.strip() for s in cc.split(",")) if p and p.lower() not in _LAYOUT_NOISE)
    tier4 = _from_text_field(cleaned)
    return tier4
