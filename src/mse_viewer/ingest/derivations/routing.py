"""Cards-vs-Tokens routing decision."""
from __future__ import annotations

from mse_viewer.parser.models import ParsedCardFace


def is_token_route(face: ParsedCardFace) -> bool:
    """Return True if the card belongs in the Tokens DB.

    Decision rule (per spec):
      - super_type contains ``Token`` (case-insensitive) → tokens DB.
      - rarity == ``special`` is a *warning* (the user picks the DB) — not handled
        here.
    """
    return "token" in (face.super_type or "").lower()
