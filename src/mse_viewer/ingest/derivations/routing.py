"""Cards-vs-Tokens routing decision."""
from __future__ import annotations

from mse_viewer.parser.models import ParsedCardFace


def is_token_route(face: ParsedCardFace) -> bool:
    """Return True if the card belongs in the Tokens DB.

    Decision rule:
      - super_type contains ``Token`` (case-insensitive) → tokens DB.
      - super_type contains ``Emblem`` → tokens DB. Emblems are produced by
        planeswalkers, share a token-shaped row schema, and never want the
        rarity:special prompt.
      - super_type contains ``Evo-T`` → tokens DB. Evo-T variants share their
        namesake card's name; the cross-link to the Cards-DB original is
        established at commit time (see ``pipeline.apply_evo_t_cross_link``).
      - rarity == ``special`` is a *warning* (the user picks the DB) — not
        handled here.
    """
    s = (face.super_type or "").lower()
    return "token" in s or "emblem" in s or is_evo_t(face)


def is_evo_t(face: ParsedCardFace) -> bool:
    """Return True if the card's super_type marks it as an Evo-T variant."""
    return "evo-t" in (face.super_type or "").lower()
