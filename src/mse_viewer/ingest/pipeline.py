"""Per-card commit step: take a FacePreview (post-modal) and write it to the DB."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mse_viewer.parser.models import ParsedCardFace, ParsedKeyword
from mse_viewer.repository import (
    CardRepository,
    DeckRepository,
    KeywordRepository,
    LogRepository,
    TokenRepository,
)
from mse_viewer.repository._helpers import append_unique, normalize_set_name

from .derivations.design_type import playbook_key
from .derivations.identity import next_collision_suffix
from .derivations.routing import is_evo_t
from .playbook import PlaybookStore
from .preview import FacePreview, Route
from .warnings import WarningKind

logger = logging.getLogger(__name__)


@dataclass
class CommitResult:
    route: Route
    record_id: int | None
    skipped: bool = False
    reason: str | None = None
    log_entry_id: int | None = None


class IngestRepos:
    """Bag of repositories, passed to the pipeline so callers don't import each."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cards = CardRepository(db)
        self.tokens = TokenRepository(db)
        self.keywords = KeywordRepository(db)
        self.decks = DeckRepository(db)
        self.log = LogRepository(db)
        self.playbook = PlaybookStore(db)


# ---------------------------------------------------------------------------
# Keyword pre-pass (called once before per-card commits)
# ---------------------------------------------------------------------------


def commit_keywords(parsed: list[ParsedKeyword], repos: IngestRepos) -> dict[str, int]:
    """Upsert all keyword definitions; returns ``match-string → keyword.id``."""
    out: dict[str, int] = {}
    for p in parsed:
        kw = repos.keywords.upsert_from_parsed(p)
        out[p.name] = kw.id
    return out


def log_rejected_keywords(rejected: list[str], repos: IngestRepos) -> None:
    """Phase 1.6 prompt 3 change 13: log the keyword definitions we deleted
    at parse time so the user can audit. One log entry per rejected match
    string."""
    for name in rejected:
        repos.log.create_action(
            title=f"Rejected keyword definition: {name!r}",
            body="This keyword:match identity is on the explicit reject list "
            "and was dropped from the file before ingest.",
            payload={"match": name, "reason": "keyword_reject_list"},
        )


def resolve_keyword_refs_for_face(
    face: ParsedCardFace,
    repos: IngestRepos,
) -> tuple[list[int], list[str], list[str]]:
    """For every ``<key>`` reference on the face, return ``(keyword_ids,
    stub_names_created, rejected_refs)``.

    Resolution uses :meth:`KeywordRepository.find_for_card_ref` so that
    parameterized references like ``Cleave 1RR`` link to a single
    ``Cleave <atom-param>cost</atom-param>`` definition rather than
    creating one stub per concrete value (init_prompt_4 #9/#10).

    Phase 1.6 prompt 3 change 13: refs matching the explicit reject-list
    are dropped here and returned in ``rejected_refs`` so the caller can
    log them — they are NOT linked into ``keyword_ids``.
    """
    from mse_viewer.parser.keyword_rejects import is_rejected_ref

    ids: list[int] = []
    stubs_created: list[str] = []
    rejected_refs: list[str] = []
    reminders = face.keyword_reminders or {}
    for ref in face.keyword_refs:
        if is_rejected_ref(ref):
            rejected_refs.append(ref)
            continue
        reminder = reminders.get(ref.lower())
        existing = repos.keywords.find_for_card_ref(ref)
        if existing is None:
            stub = repos.keywords.ensure_stub(ref, reminder=reminder)
            stubs_created.append(stub.name)
            kid = stub.id
            logger.info(
                "keyword_ref card=%r ref=%r reminder=%r → new stub id=%s is_stub=%s",
                face.name, ref, reminder, stub.id, stub.is_stub,
            )
        else:
            # Backfill the reminder onto a pre-existing stub if it didn't have one.
            repos.keywords.maybe_backfill_reminder(existing, reminder)
            kid = existing.id
            logger.info(
                "keyword_ref card=%r ref=%r reminder=%r → existing id=%s is_stub=%s",
                face.name, ref, reminder, existing.id, existing.is_stub,
            )
        if kid not in ids:
            ids.append(kid)
    return ids, stubs_created, rejected_refs


# ---------------------------------------------------------------------------
# Per-face commit
# ---------------------------------------------------------------------------


def commit_face(
    preview: FacePreview,
    *,
    set_name: str,
    pwl_default_for_rarity: dict[str, int] | None,
    repos: IngestRepos,
) -> CommitResult:
    """Persist a face after the user has resolved its review modal."""
    face = preview.face

    # 1) "Do Not Read": skip and log.
    if face.notes.do_not_read:
        entry = repos.log.create_action(
            title=f"Skipped (Do Not Read): {face.name}",
            body=face.raw_notes or None,
            payload={"raw_block_excerpt": preview.face.model_dump(mode="json")},
        )
        return CommitResult(
            route=preview.route,
            record_id=None,
            skipped=True,
            reason="do_not_read",
            log_entry_id=entry.id,
        )

    # 2) User explicitly rejected the card from the modal.
    if preview.rejected:
        entry = repos.log.create_action(
            title=f"Rejected from review: {face.name}",
            body=preview.warnings.warnings[0].message if preview.warnings else None,
            payload={"face": preview.face.model_dump(mode="json")},
        )
        return CommitResult(
            route=preview.route,
            record_id=None,
            skipped=True,
            reason="rejected",
            log_entry_id=entry.id,
        )

    # 3) Resolve final identity. ``route_override`` (set by the rarity:special
    #    DB picker in the modal) wins over the auto-derived route.
    effective_route = preview.route_override or preview.route
    repo = repos.tokens if effective_route == "token" else repos.cards
    existing_identities = repo.existing_identities()
    proposed = preview.proposed_identity

    resolution = preview.collision_resolution or ("update" if proposed in existing_identities else "fresh")

    if resolution == "rename":
        proposed = next_collision_suffix(proposed, existing_identities)
        existing = None
    elif resolution in ("update", "alternate"):
        existing = repo.find_by_identity(proposed)
    else:  # "fresh"
        existing = None

    # 4) Resolve keyword references → ids + stub log entries.
    keyword_ids, stub_names, rejected_refs = resolve_keyword_refs_for_face(face, repos)
    for stub in stub_names:
        repos.log.create_action(
            title=f"Define keyword: {stub}",
            body=f"Auto-created stub keyword from card {face.name!r}.",
            payload={"keyword_ref": stub, "card_name": face.name},
        )
    for ref in rejected_refs:
        repos.log.create_action(
            title=f"Rejected keyword on {face.name!r}: {ref!r}",
            body="The reference matches the explicit keyword reject-list and "
            "was not linked. Edit the source card if this was intentional.",
            payload={"keyword_ref": ref, "card_name": face.name, "reason": "keyword_reject_list"},
        )

    # 5) Compute concrete fields, applying any overrides from the modal.
    o = preview.overrides
    design_type_value = (
        o.get("design_type")
        or preview.design_type.value
        or "Custom"
    )

    # If the modal answered an unrecognized-design-type warning, remember it.
    if preview.warnings.has(WarningKind.design_type_unrecognized) and o.get("design_type"):
        key = playbook_key(face.stylesheet or "", face.styling_data or {})
        repos.playbook.design_type_remember(key, str(o["design_type"]))

    rarity = (o.get("rarity") or face.rarity or "common").strip().lower()
    pwl = face.notes.pwl
    if pwl is None and pwl_default_for_rarity:
        pwl = pwl_default_for_rarity.get(rarity)

    colors = list(o.get("colors") or preview.colors)
    notes_body = face.notes.remainder or None

    common_kwargs = dict(
        display_name=face.name,
        card_type=face.super_type or "",
        card_subtype=face.sub_type,
        colors=colors,
        casting_cost=face.casting_cost,
        power=face.power,
        toughness=face.toughness,
        flavor_text=face.flavor_text,
        rule_text=face.rule_text,
        keyword_ids=keyword_ids,
        related_cards=_canonicalize_related(list(face.related_from_notes), repos),
        design_type=design_type_value,
        notes=notes_body,
        printed=face.notes.status_printed,
        alias=face.alias,
    )
    # Card-only columns: ``starting_loyalty`` and ``sets`` apply to Card only.
    # ``sets`` was removed from Token in 0004 (Phase 1.6 prompt 3 bug 6).

    set_name_n = normalize_set_name(set_name)
    alt_art_label = preview.accept_as_alternate_label

    if existing is not None and resolution in ("update", "alternate"):
        # Update in place.
        for attr, value in common_kwargs.items():
            # Don't squash existing values with empty-on-import; only overwrite
            # when the import provides something.
            if value not in (None, "", []):
                setattr(existing, attr, value)
        # Card-only: starting_loyalty. Same empty-import guard as above.
        if effective_route == "card" and face.starting_loyalty is not None:
            existing.starting_loyalty = face.starting_loyalty
        # Tokens no longer carry a ``sets`` column — only Cards do.
        if effective_route == "card":
            repo.append_set(existing, set_name_n)
        if alt_art_label or resolution == "alternate":
            label = alt_art_label or "alternate"
            repo.append_alt_art(existing, label)
        repo.append_related(
            existing,
            _canonicalize_related(list(face.related_from_notes), repos),
        )
        _apply_evo_t_cross_link(face, route=effective_route, row=existing, repos=repos)
        _apply_emblem_cross_link(face, route=effective_route, row=existing, repos=repos)
        repos.db.flush()
        return CommitResult(route=effective_route, record_id=existing.id)

    # Fresh create. Honour ``effective_route`` (the user's modal pick beats the
    # auto-derived route) so that a card with a name collision in the Cards DB
    # can still be added to the Tokens DB without tripping cards.name UNIQUE.
    new_kwargs = {"name": proposed, **common_kwargs}
    if effective_route == "card":
        new_kwargs["rarity"] = rarity
        new_kwargs["power_level"] = pwl
        new_kwargs["starting_loyalty"] = face.starting_loyalty
        row = repos.cards.create(**new_kwargs)
    else:
        row = repos.tokens.create(**new_kwargs)

    if effective_route == "card":
        repo.append_set(row, set_name_n)
    if alt_art_label:
        repo.append_alt_art(row, alt_art_label)

    _apply_evo_t_cross_link(face, route=effective_route, row=row, repos=repos)
    _apply_emblem_cross_link(face, route=effective_route, row=row, repos=repos)
    return CommitResult(route=effective_route, record_id=row.id)


def _apply_evo_t_cross_link(
    face: ParsedCardFace,
    *,
    route: Route,
    row,
    repos: IngestRepos,
) -> None:
    """Cross-link an Evo-T variant with its namesake Card so the UI can
    navigate between the two without changing identity rules.

    Two directions, since ingest order isn't guaranteed:

    * If ``face`` is Evo-T and lands in Tokens → look up the namesake Card
      (case-insensitive match on display name) and link both ways.
    * If ``face`` lands in Cards → look up any Token with the same display
      name whose stored ``card_type`` marks it as an Evo-T and link both
      ways. Catches the case where the Evo-T was imported first.

    ``append_related`` is de-duplicating, so re-running the cross-link on
    re-import never accumulates extra entries.
    """
    if route == "token" and is_evo_t(face):
        for namesake in repos.cards.find_by_name_ci(face.name):
            repos.tokens.append_related(row, [namesake.name])
            repos.cards.append_related(namesake, [row.name])
        return
    if route == "card":
        for tok in repos.tokens.find_by_name_ci(face.name):
            if "evo-t" in (tok.card_type or "").lower():
                repos.tokens.append_related(tok, [row.name])
                repos.cards.append_related(row, [tok.name])


def _canonicalize_related(names: list[str], repos: IngestRepos) -> list[str]:
    """Auto-correct casing on related-card names against the existing rows.

    Phase 1.6 prompt 3 bug 5: a related entry written as ``"Ackey The Archer"``
    that resolves (CI) to a Card stored as ``"Ackey the Archer"`` should be
    rewritten to the stored capitalization. Misspells are NOT corrected — only
    casing. We try Cards first, fall back to Tokens. Names that don't resolve
    are left alone so the missing-related view can still flag them.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        if not raw:
            continue
        candidate = raw.strip()
        if not candidate:
            continue
        canonical = candidate
        for repo in (repos.cards, repos.tokens):
            hit = repo.find_by_identity(candidate)
            if hit is not None:
                canonical = hit.name
                break
            ci = repo.find_by_name_ci(candidate)
            if ci:
                canonical = ci[0].name
                break
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return out


def _apply_emblem_cross_link(
    face: ParsedCardFace,
    *,
    route: Route,
    row,
    repos: IngestRepos,
) -> None:
    """Cross-link an Emblem with the planeswalker named in its subtype.

    The face-level parser already wrote the subtype into ``related_from_notes``
    so the emblem's row carries the link forward. This helper writes the
    reverse direction onto the Card row when it exists, so the planeswalker
    detail page surfaces the emblem under Related cards. Re-runnable
    (``append_related`` de-dupes).

    No-op when the face isn't an Emblem; no-op when the named planeswalker
    isn't in the Cards DB yet (the emblem-side ``(missing)`` annotation will
    surface until the planeswalker is imported).
    """
    if route != "token":
        return
    if "emblem" not in (face.super_type or "").lower():
        return
    sub = (face.sub_type or "").strip()
    if not sub:
        return
    for namesake in repos.cards.find_by_name_ci(sub):
        repos.cards.append_related(namesake, [row.name])
        repos.tokens.append_related(row, [namesake.name])
