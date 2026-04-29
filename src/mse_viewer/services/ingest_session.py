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

from mse_viewer.ingest.pipeline import IngestRepos, commit_face, commit_keywords
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
    committed: list[int] = field(default_factory=list)  # face indexes already committed
    skipped: list[int] = field(default_factory=list)
    finished: bool = False

    @property
    def total(self) -> int:
        return len(self.previews)

    def current(self) -> FacePreview | None:
        if self.cursor >= self.total:
            return None
        return self.previews[self.cursor]

    def advance(self) -> None:
        self.cursor += 1
        if self.cursor >= self.total:
            self.finished = True


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
    ) -> IngestSession:
        # Pre-pass: write all keyword definitions so cards can FK them.
        keyword_ids = commit_keywords(parsed.keywords, repos)
        repos.db.commit()

        # Build per-face previews up-front.
        existing_card_ids = repos.cards.existing_identities()
        existing_token_ids = repos.tokens.existing_identities()
        previews: list[FacePreview] = []
        for card in parsed.cards:
            for face in card.faces:
                previews.append(
                    build_preview(
                        face,
                        header=parsed.header,
                        existing_card_identities=existing_card_ids,
                        existing_token_identities=existing_token_ids,
                        playbook_lookup=repos.playbook.design_type_lookup,
                    )
                )

        session = IngestSession(
            id=uuid4().hex,
            parsed=parsed,
            set_name=set_name,
            pwl_defaults=pwl_defaults,
            previews=previews,
            keyword_ids=keyword_ids,
        )
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

    def discard(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


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


# Module-level singleton store. The FastAPI dependency below returns this one.
_store = IngestSessionStore()


def get_session_store() -> IngestSessionStore:
    return _store


def session_iter(store: IngestSessionStore) -> Iterable[IngestSession]:
    return list(store._sessions.values())  # noqa: SLF001 - simple debug accessor
