"""Deck-mode ingest helpers.

A deck file is structurally a regular MSE set file: a series of ``card:``
blocks. Quantity is encoded by repeating the block (a 4-of Zap appears as
four ``card:`` entries named Zap). This module collapses repeats into a
quantity map and dedupes the parsed-card list so the existing review pipeline
runs once per unique card.

Cards already in the Cards DB are skipped entirely — they don't need a review
modal, only a deck-card link. Only previously-unknown cards reach the
pipeline; the deck row is then created at session-finish time using the
collapsed quantities and the (now-resolvable) Card ids.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mse_viewer.parser.models import ParsedCard, ParsedSet


@dataclass
class DeckIngestPlan:
    """Companion data the session keeps so it can finalize a Deck row.

    ``meta`` is the kwargs-bag for ``Deck(...)`` (name, format, theme, etc.).
    ``quantities`` is ``card-name → count`` covering *every* unique card the
    deck file mentioned, including ones already in the Cards DB. ``missing``
    starts as the same set of names; entries are dropped as Cards become
    resolvable, and any survivors at finalize time become "card not in DB"
    log entries.
    """

    meta: dict
    quantities: dict[str, int] = field(default_factory=dict)
    missing: set[str] = field(default_factory=set)


def collapse_deck(
    parsed: ParsedSet,
    *,
    existing_card_names: set[str],
    existing_token_names: set[str] | None = None,
) -> tuple[ParsedSet, dict[str, int]]:
    """Collapse repeated ``card:`` blocks by name and return (deduped_set,
    quantities). Only cards *not* already in the Cards or Tokens DB land in
    the deduped set's ``cards`` list — those are what the review pipeline
    will walk. The quantities map covers every unique card name regardless.

    Phase 1.6 prompt 4 item 7: tokens are also matched so a deck that
    references a token-only card doesn't get sent through review as if it
    were a brand-new Card row (which would clash with the same-name Token).
    """
    quantities: dict[str, int] = {}
    seen: set[str] = set()
    new_cards: list[ParsedCard] = []
    existing_ci: set[str] = {n.lower() for n in existing_card_names if n}
    if existing_token_names:
        existing_ci |= {n.lower() for n in existing_token_names if n}
    for card in parsed.cards:
        if not card.faces:
            continue
        # Identity for the deck link is the *primary face*'s name. DFC decks
        # are unusual but we still collapse on face-1 — face-2 rides along.
        name = card.faces[0].name
        if not name:
            continue
        quantities[name] = quantities.get(name, 0) + 1
        if name in seen:
            continue
        seen.add(name)
        if name.lower() in existing_ci:
            continue
        new_cards.append(card)
    deduped = ParsedSet(
        header=parsed.header,
        keywords=parsed.keywords,
        cards=new_cards,
    )
    return deduped, quantities
