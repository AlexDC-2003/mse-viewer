"""In-memory ingest sessions.

A session holds the parsed set + per-face previews that the review UI walks
through one at a time.  We keep it in process memory keyed by a UUID; this is
appropriate for a single-user localhost app and means the session vanishes if
the server restarts (which is fine for Phase 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable
from uuid import uuid4

from mse_viewer.ingest.deck import DeckIngestPlan
from mse_viewer.ingest.pipeline import (
    IngestRepos,
    commit_face,
    commit_keywords,
    log_rejected_keywords,
)
from mse_viewer.ingest.preview import FacePreview, build_preview
from mse_viewer.parser.models import ParsedSet


@dataclass
class IngestSession:
    id: str
    parsed: ParsedSet
    set_name: str
    pwl_defaults: dict[str, int]
    previews: list[FacePreview] = field(default_factory=list)
    cursor: int = 0
    keyword_ids: dict[str, int] = field(default_factory=dict)
    committed: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    auto_committed_count: int = 0
    parsed_total: int = 0
    finished: bool = False
    # Deck-mode companion data. None for plain set ingests; populated when the
    # upload arrived through ``mode=deck`` and finalized once the review queue
    # drains (see :func:`finalize_deck`).
    deck_plan: DeckIngestPlan | None = None
    deck_id: int | None = None

    @property
    def review_total(self) -> int:
        """Number of cards in the manual review queue."""
        return len(self.previews)

    @property
    def review_count(self) -> int:
        """Number of cards still queued for manual review."""
        return max(0, self.review_total - self.cursor)

    def current(self) -> FacePreview | None:
        if self.cursor >= self.review_total:
            return None
        return self.previews[self.cursor]

    def advance(self) -> None:
        self.cursor += 1
        if self.cursor >= self.review_total:
            self.finished = True


def _row_snapshot(row) -> dict:
    """Snapshot a Card / Token row to the same shape as
    :func:`mse_viewer.ingest.preview._face_snapshot` for diff rendering."""
    return {
        "card_type": row.card_type,
        "card_subtype": row.card_subtype,
        "colors": list(row.colors or []),
        "casting_cost": row.casting_cost,
        "power": row.power,
        "toughness": row.toughness,
        "flavor_text": row.flavor_text,
        "rule_text": row.rule_text,
        "design_type": row.design_type,
        "rarity": getattr(row, "rarity", None),
        "alias": row.alias,
        "starting_loyalty": getattr(row, "starting_loyalty", None),
        "related_cards": list(row.related_cards or []),
        "printed": bool(getattr(row, "printed", False)),
    }


def _needs_review(preview: FacePreview) -> bool:
    """A preview needs the user only when there's a real warning OR the user
    explicitly asked to be stopped (Do Not Read is auto-handled separately).
    """
    if preview.face.notes.do_not_read:
        # Auto-skipped + logged; never shown in the UI.
        return False
    return bool(preview.warnings)


class IngestSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, IngestSession] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        parsed: ParsedSet,
        set_name: str,
        pwl_defaults: dict[str, int],
        repos: IngestRepos,
        deck_plan: DeckIngestPlan | None = None,
    ) -> IngestSession:
        # Pre-pass: write all keyword definitions so cards can FK them.
        keyword_ids = commit_keywords(parsed.keywords, repos)
        if parsed.rejected_keywords:
            log_rejected_keywords(parsed.rejected_keywords, repos)
        repos.db.commit()

        # Build per-face previews up-front.
        existing_card_ids = repos.cards.existing_identities()
        existing_token_ids = repos.tokens.existing_identities()

        def _existing_lookup(name: str, route: str):
            repo = repos.tokens if route == "token" else repos.cards
            row = repo.find_by_identity(name)
            if row is None:
                return None
            return _row_snapshot(row)

        all_previews: list[FacePreview] = []
        for card in parsed.cards:
            for face in card.faces:
                all_previews.append(
                    build_preview(
                        face,
                        header=parsed.header,
                        existing_card_identities=existing_card_ids,
                        existing_token_identities=existing_token_ids,
                        playbook_lookup=repos.playbook.design_type_lookup,
                        existing_lookup=_existing_lookup,
                    )
                )

        # Auto-commit every preview that doesn't need a review, *in order*, so
        # that subsequent identity-collision checks against the in-DB state
        # remain accurate. Surviving previews (those needing review) feed the
        # modal queue.
        review_queue: list[FacePreview] = []
        auto_count = 0
        skipped: list[int] = []
        committed: list[int] = []
        for preview in all_previews:
            if _needs_review(preview):
                review_queue.append(preview)
                continue
            result = commit_face(
                preview,
                set_name=set_name,
                pwl_default_for_rarity=pwl_defaults,
                repos=repos,
            )
            auto_count += 1
            if result.skipped:
                skipped.append(auto_count - 1)
            elif result.record_id is not None:
                committed.append(result.record_id)
        repos.db.commit()

        session = IngestSession(
            id=uuid4().hex,
            parsed=parsed,
            set_name=set_name,
            pwl_defaults=pwl_defaults,
            previews=review_queue,
            keyword_ids=keyword_ids,
            auto_committed_count=auto_count,
            committed=committed,
            skipped=skipped,
            parsed_total=len(all_previews),
            deck_plan=deck_plan,
        )
        if not review_queue:
            session.finished = True
            if deck_plan is not None:
                _finalize_deck(session, repos)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> IngestSession | None:
        return self._sessions.get(session_id)

    def commit_current(
        self,
        session: IngestSession,
        repos: IngestRepos,
        *,
        action: str,
        modal_data: dict,
    ) -> None:
        preview = session.current()
        if preview is None:
            return
        # Apply modal answers to the preview before commit.
        _apply_modal_answers(preview, action=action, data=modal_data)
        result = commit_face(
            preview,
            set_name=session.set_name,
            pwl_default_for_rarity=session.pwl_defaults,
            repos=repos,
        )
        repos.db.commit()
        if result.skipped:
            session.skipped.append(session.cursor)
        else:
            if result.record_id is not None:
                session.committed.append(result.record_id)
        session.advance()
        if session.finished and session.deck_plan is not None and session.deck_id is None:
            _finalize_deck(session, repos)

    def discard(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


def _finalize_deck(session: IngestSession, repos: IngestRepos) -> None:
    """Create the Deck row + DeckCard links for a deck-mode session.

    Runs once, when the review queue has drained. For each name in the
    quantities map we resolve the Card via identity (case-insensitive
    fallback), link it with the captured quantity, and log any names that
    didn't resolve so the user can fix them after the fact.
    """
    plan = session.deck_plan
    if plan is None:
        return
    # Re-check name conflict at finalize time — the user may have been
    # writing decks in parallel.
    if repos.decks.find_by_name(plan.meta["name"]):
        repos.log.create_action(
            title=f"Deck not created: name {plan.meta['name']!r} taken",
            body="Resolve manually via Decks → Edit and re-run finalize.",
            payload={"deck_meta": plan.meta},
        )
        repos.db.commit()
        return
    deck = repos.decks.create(**plan.meta)
    missing: list[str] = []
    for name, qty in plan.quantities.items():
        card = repos.cards.find_by_identity(name)
        if card is None:
            ci = repos.cards.find_by_name_ci(name)
            if ci:
                card = ci[0]
        if card is None:
            missing.append(name)
            continue
        repos.decks.add_card(deck, card.id, quantity=qty)
    if missing:
        repos.log.create_action(
            title=f"Deck {deck.name!r}: {len(missing)} card(s) not linked",
            body="\n".join(f"{n!r} (no Card row found)" for n in missing),
            payload={"deck_id": deck.id, "missing": missing},
        )
    repos.db.commit()
    session.deck_id = deck.id


def _apply_modal_answers(preview: FacePreview, *, action: str, data: dict) -> None:
    if action == "reject":
        preview.rejected = True
        return
    # Override fields are accepted as a flat dict; only known keys are honored.
    overrides: dict[str, object] = {}
    for key in ("design_type", "rarity"):
        v = data.get(key)
        if v:
            overrides[key] = v
    raw_colors = data.get("colors")
    if raw_colors:
        overrides["colors"] = [c.strip() for c in str(raw_colors).split(",") if c.strip()]
    preview.overrides = overrides

    coll = data.get("collision_resolution") or None
    if coll:
        preview.collision_resolution = coll

    label = (data.get("alt_art_label") or "").strip() or None
    if label:
        preview.accept_as_alternate_label = label
        preview.collision_resolution = preview.collision_resolution or "alternate"

    route_override = (data.get("route_override") or "").strip().lower() or None
    if route_override in ("card", "token"):
        preview.route_override = route_override  # type: ignore[assignment]


# Module-level singleton store. The FastAPI dependency below returns this one.
_store = IngestSessionStore()


def get_session_store() -> IngestSessionStore:
    return _store


def session_iter(store: IngestSessionStore) -> Iterable[IngestSession]:
    return list(store._sessions.values())  # noqa: SLF001 - simple debug accessor
